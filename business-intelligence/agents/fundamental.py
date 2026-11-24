"""Fundamental-analysis agent: valuation (EPS, P/E, P/BV, Graham value),
dividends, liquidity, sector/market relative performance and floor-sheet
broker activity. Reads only the database: fundamentals come from
market_fundamental_daily / market_corporate_action (nepse-service)."""
from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta
from statistics import median
from typing import Any

import numpy as np

import market_data
from common import pct
from agents.base import AgentContext, fmt_pct, fmt_price, score_signals, section, signal, top_signals_text

AGENT = "fundamental"
PERIODS = (("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365))


def _period_returns(dates: list[date], closes: np.ndarray, today: date) -> dict[str, float | None]:
    out = {}
    for label, days in PERIODS:
        start = today - timedelta(days=days)
        idx = next((i for i, d in enumerate(dates) if d >= start), None)
        out[label] = pct(float(closes[-1]), float(closes[idx])) if idx is not None and idx < len(closes) - 1 else None
    return out


def analyze(symbol: str, features: dict[str, dict[str, Any]], info: dict[str, Any], live_price: float | None) -> dict[str, Any]:
    today = date.today()
    sig: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    charts: dict[str, Any] = {}
    data: dict[str, Any] = {}
    notes: list[str] = []
    sector = info.get("sector_name")
    fund = market_data.fundamentals(symbol)
    latest = fund["latest"]
    price = live_price or (latest or {}).get("market_price")

    # --- valuation
    if "valuation" in features:
        if not latest:
            notes.append("no fundamentals captured yet (nepse-service CompanyFundamentalsWorkflow)")
        else:
            eps, bv = latest.get("eps"), latest.get("book_value")
            pe = price / eps if price and eps and eps > 0 else None
            pbv = price / bv if price and bv and bv > 0 else None
            graham = math.sqrt(22.5 * eps * bv) if eps and bv and eps > 0 and bv > 0 else None
            metrics.update({
                "price": price, "eps": eps, "eps_period": latest.get("eps_period"), "pe_ratio": pe,
                "book_value": bv, "pbv": pbv, "earnings_yield_pct": eps / price * 100 if eps and price else None,
                "graham_value": graham, "graham_margin_pct": pct(graham, price) if graham else None,
                "market_cap": latest.get("market_cap"), "shares_outstanding": latest.get("shares_outstanding"),
                "fundamentals_date": latest.get("trade_date"),
                "high_52w": latest.get("high_52w"), "low_52w": latest.get("low_52w"),
            })
            if eps is not None and eps <= 0:
                sig.append(signal("eps", f"Negative earnings (EPS {eps:.2f})", "bearish", 0.7, eps, weight=1.5))
            if graham and price:
                margin = (graham / price - 1) * 100
                if margin >= 15:
                    sig.append(signal("graham", f"Price {abs(margin):.0f}% below the Graham value ({fmt_price(graham)})", "bullish", min(0.7, 0.3 + margin / 100), graham))
                elif margin <= -40:
                    sig.append(signal("graham", f"Price {abs(margin):.0f}% above the Graham value ({fmt_price(graham)})", "bearish", min(0.6, 0.2 + abs(margin) / 200), graham))
            hist = [h for h in fund["history"] if h["pe_ratio"]]
            charts["valuation_history"] = fund["history"]
            if len(hist) >= 40 and pe:
                pes = np.array([h["pe_ratio"] for h in hist if h["pe_ratio"] and h["pe_ratio"] > 0])
                if pes.size >= 40:
                    rank = float((pes < pe).mean() * 100)
                    metrics["pe_percentile_1y"] = rank
                    if rank <= 15:
                        sig.append(signal("pe_history", f"P/E near its 1-year low (percentile {rank:.0f})", "bullish", 0.35, pe))
                    elif rank >= 85:
                        sig.append(signal("pe_history", f"P/E near its 1-year high (percentile {rank:.0f})", "bearish", 0.35, pe))

    # --- sector valuation
    if "peer_valuation" in features and sector and latest:
        peers = [p for p in market_data.sector_fundamentals(sector) if p["symbol"] != symbol]
        peers = sorted(peers, key=lambda p: -(p.get("market_cap") or 0))[: features["peer_valuation"]["max_peers"]]
        pe_list = [p["pe_ratio"] for p in peers if p.get("pe_ratio") and 0 < p["pe_ratio"] < 500]
        pbv_list = [p["pbv"] for p in peers if p.get("pbv") and p["pbv"] > 0]
        peer_pe, peer_pbv = (median(pe_list) if pe_list else None), (median(pbv_list) if pbv_list else None)
        metrics.update({"sector_median_pe": peer_pe, "sector_median_pbv": peer_pbv, "peer_count": len(peers)})
        data["peers"] = peers
        pe, pbv = metrics.get("pe_ratio"), metrics.get("pbv")
        if pe and peer_pe:
            rel = (pe / peer_pe - 1) * 100
            metrics["pe_vs_sector_pct"] = rel
            if rel <= -20:
                sig.append(signal("peer_pe", f"P/E {pe:.1f} is {abs(rel):.0f}% below the sector median {peer_pe:.1f}", "bullish", min(0.7, 0.3 + abs(rel) / 100), pe, weight=1.3))
            elif rel >= 25:
                sig.append(signal("peer_pe", f"P/E {pe:.1f} is {rel:.0f}% above the sector median {peer_pe:.1f}", "bearish", min(0.7, 0.3 + rel / 150), pe, weight=1.3))
        if pbv and peer_pbv:
            rel = (pbv / peer_pbv - 1) * 100
            metrics["pbv_vs_sector_pct"] = rel
            if abs(rel) >= 25:
                sig.append(signal("peer_pbv", f"P/BV {pbv:.2f} vs. sector median {peer_pbv:.2f}", "bullish" if rel < 0 else "bearish", 0.3, pbv))
        charts["peer_valuation"] = [{"symbol": p["symbol"], "pe_ratio": p.get("pe_ratio"), "pbv": p.get("pbv")} for p in peers] + (
            [{"symbol": symbol, "pe_ratio": pe, "pbv": pbv, "self": True}] if pe or pbv else [])

    # --- dividends
    if "dividends" in features:
        actions = fund["corporate_actions"]
        cash = [a for a in actions if a["action_type"] == "cash_dividend" and a["value_pct"]]
        bonus = [a for a in actions if a["action_type"] == "bonus" and a["value_pct"]]
        by_fy: dict[str, dict[str, float]] = {}
        for a in actions:
            if a["action_type"] in ("cash_dividend", "bonus") and a["value_pct"]:
                by_fy.setdefault(a["fiscal_year"], {"cash_dividend": 0.0, "bonus": 0.0})[a["action_type"]] += a["value_pct"]
        charts["dividend_history"] = [{"fiscal_year": fy, **v} for fy, v in sorted(by_fy.items())][-10:]
        paid_up = (latest or {}).get("paidup_value") or 100.0
        last_cash = (latest or {}).get("cash_dividend_pct")
        dy = last_cash * paid_up / 100 / price * 100 if last_cash is not None and price else None
        years = sorted(by_fy)[-5:]
        payout_years = sum(1 for fy in years if by_fy[fy]["cash_dividend"] > 0 or by_fy[fy]["bonus"] > 0)
        metrics.update({"cash_dividend_pct": last_cash, "bonus_pct": (latest or {}).get("bonus_pct"),
                        "dividend_yield_pct": dy, "payout_years_of_last_5": payout_years if years else None})
        if dy is not None:
            if dy >= 5:
                sig.append(signal("dividend_yield", f"Dividend yield {dy:.1f}%", "bullish", min(0.6, dy / 15), dy))
            elif dy == 0 and not cash:
                sig.append(signal("dividend_yield", "No cash dividend on record", "neutral", 0.2, 0))
        if years and payout_years >= 4:
            sig.append(signal("dividend_record", f"Paid dividend/bonus in {payout_years} of the last {len(years)} fiscal years", "bullish", 0.3))
        data["bonus_history"] = bonus[:10]
        data["cash_history"] = cash[:10]

    # --- liquidity
    if "liquidity" in features:
        n = features["liquidity"]["sessions"]
        bars = market_data.daily_bars(symbol, "raw", start=today - timedelta(days=n * 2 + 30), include_live=False)
        if len(bars) >= 10:
            t, v = bars.turnover[-n:], bars.volume[-n:]
            recent = np.nanmean(t[-20:]) if np.isfinite(t[-20:]).any() else np.nan
            older = np.nanmean(t[:-20]) if t.size > 25 and np.isfinite(t[:-20]).any() else np.nan
            metrics.update({"avg_turnover": float(np.nanmean(t)), "avg_volume": float(np.nanmean(v)),
                            "turnover_trend_pct": pct(float(recent), float(older)) if not (np.isnan(older) or np.isnan(recent)) else None,
                            "zero_volume_sessions": int(np.sum(np.nan_to_num(v) == 0))})
            if metrics["avg_turnover"] < 2e6:
                sig.append(signal("liquidity", f"Thin liquidity (avg turnover NPR {metrics['avg_turnover'] / 1e6:.1f}M)", "bearish", 0.3,
                                  metrics["avg_turnover"], "wide spreads / hard to exit"))
            trend = metrics.get("turnover_trend_pct")
            if trend is not None and trend >= 50:
                sig.append(signal("turnover_trend", f"Turnover up {trend:.0f}% (last 20 sessions vs. before)", "neutral", 0.3, trend,
                                  "rising interest; direction from price"))

    # --- sector & market performance
    if "sector_comparison" in features:
        start = today - timedelta(days=400)
        bars = market_data.daily_bars(symbol, "adjusted", start=start, include_live=False)
        if len(bars) >= 30:
            own = _period_returns(bars.dates, bars.close, today)
            idx_dates, idx_close = market_data.index_closes("NEPSE", start)
            nepse = _period_returns(idx_dates, idx_close, today) if len(idx_close) > 30 else {}
            peers = market_data.sector_peers(sector, exclude=symbol) if sector else []
            peer_series = market_data.adjusted_closes_many(peers, start)
            peer_returns = {s: _period_returns(d, c, today) for s, (d, c) in peer_series.items() if len(c) > 30}
            sector_median = {lbl: (median([r[lbl] for r in peer_returns.values() if r.get(lbl) is not None])
                                   if any(r.get(lbl) is not None for r in peer_returns.values()) else None) for lbl, _ in PERIODS}
            rank_3m = None
            if own.get("3M") is not None and peer_returns:
                vals = [r["3M"] for r in peer_returns.values() if r.get("3M") is not None]
                rank_3m = float(np.mean([own["3M"] > v for v in vals]) * 100) if vals else None
            metrics.update({"returns": own, "nepse_returns": nepse, "sector_median_returns": sector_median,
                            "sector_rank_3m_pct": rank_3m, "sector_peer_count": len(peer_returns)})
            charts["relative_performance"] = [{"period": lbl, "stock": own.get(lbl), "sector": sector_median.get(lbl), "nepse": nepse.get(lbl)}
                                              for lbl, _ in PERIODS]
            rel3 = (own["3M"] - nepse["3M"]) if own.get("3M") is not None and nepse.get("3M") is not None else None
            if rel3 is not None:
                metrics["relative_strength_3m_pct"] = rel3
                if abs(rel3) >= 5:
                    sig.append(signal("relative_strength", f"{'Outperformed' if rel3 > 0 else 'Underperformed'} NEPSE by {abs(rel3):.1f} pts over 3 months",
                                      "bullish" if rel3 > 0 else "bearish", min(0.6, 0.25 + abs(rel3) / 40), rel3))
            if rank_3m is not None and (rank_3m >= 80 or rank_3m <= 20):
                sig.append(signal("sector_rank", f"3-month return in the {'top' if rank_3m >= 80 else 'bottom'} fifth of {sector}",
                                  "bullish" if rank_3m >= 80 else "bearish", 0.35, rank_3m))

    # --- broker activity (floor sheet)
    if "broker_activity" in features:
        f = features["broker_activity"]
        flows = market_data.broker_flows(symbol, today - timedelta(days=f["days"]))
        brokers, totals = flows["brokers"], flows["totals"]
        qty = float(totals.get("quantity") or 0)
        if brokers and qty:
            by_net = sorted(brokers, key=lambda b: -b["net"])
            top_buy = sorted(brokers, key=lambda b: -b["bought"])[:5]
            buy_conc = sum(b["bought"] for b in top_buy) / qty * 100
            sell_conc = sum(b["sold"] for b in sorted(brokers, key=lambda b: -b["sold"])[:5]) / qty * 100
            top_net = by_net[: f["top"]]
            top_net_share = sum(b["net"] for b in by_net[:5] if b["net"] > 0) / qty * 100
            metrics.update({"broker_days": f["days"], "broker_sessions": totals.get("sessions"), "broker_trades": totals.get("trades"),
                            "broker_quantity": qty, "top5_buy_concentration_pct": buy_conc, "top5_sell_concentration_pct": sell_conc,
                            "top5_net_accumulation_pct": top_net_share})
            charts["broker_net"] = top_net + by_net[-f["top"]:][::-1]
            data["broker_totals"] = totals
            if buy_conc - sell_conc >= 10 and top_net_share >= 15:
                sig.append(signal("broker_accumulation", f"Concentrated buying: top-5 buyers took {buy_conc:.0f}% of volume (sellers {sell_conc:.0f}%)",
                                  "bullish", min(0.6, 0.3 + (buy_conc - sell_conc) / 60), buy_conc, "possible accumulation by a few brokers"))
            elif sell_conc - buy_conc >= 10:
                sig.append(signal("broker_distribution", f"Concentrated selling: top-5 sellers {sell_conc:.0f}% vs. buyers {buy_conc:.0f}%",
                                  "bearish", min(0.6, 0.3 + (sell_conc - buy_conc) / 60), sell_conc, "possible distribution"))

    # --- corporate actions from the adjusted-price history
    if "corporate_actions" in features:
        bars = market_data.daily_bars(symbol, "adjusted", start=today - timedelta(days=365 * 5), include_live=False)
        events = []
        for i in range(1, len(bars)):
            a, b = bars.factor[i - 1], bars.factor[i]
            if a and b and abs(a / b - 1) > 0.01:
                events.append({"date": bars.dates[i], "adjustment_pct": (b / a - 1) * 100})
        data["price_adjustments"] = events[-10:]

    score = score_signals(sig)
    parts = []
    if metrics.get("pe_ratio"):
        parts.append(f"P/E {metrics['pe_ratio']:.1f}" + (f" (sector median {metrics['sector_median_pe']:.1f})" if metrics.get("sector_median_pe") else ""))
    if metrics.get("pbv"):
        parts.append(f"P/BV {metrics['pbv']:.2f}")
    if metrics.get("eps") is not None:
        parts.append(f"EPS {metrics['eps']:.2f} ({metrics.get('eps_period') or 'latest'})")
    if metrics.get("dividend_yield_pct") is not None:
        parts.append(f"dividend yield {metrics['dividend_yield_pct']:.1f}%")
    if metrics.get("relative_strength_3m_pct") is not None:
        parts.append(f"3M vs. NEPSE {fmt_pct(metrics['relative_strength_3m_pct'])}")
    if sig:
        parts.append("key signals: " + top_signals_text(sig))
    parts += notes
    status = "ok" if (latest or metrics) else "no_data"
    return section(AGENT, status, summary=("; ".join(parts) + ".") if parts else "No fundamental data available.",
                   score=score, signals=sig, metrics=metrics, charts=charts, data=data, features=list(features))


async def run(ctx: AgentContext) -> dict[str, Any]:
    quote = await asyncio.to_thread(market_data.live_quote, ctx.symbol)
    live = float(quote["last_traded_price"]) if quote and quote.get("last_traded_price") else None
    return await asyncio.to_thread(analyze, ctx.symbol, ctx.features(AGENT), ctx.info, live)
