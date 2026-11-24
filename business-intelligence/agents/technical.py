"""Technical-analysis agent: indicators, levels and patterns on daily bars
(with today's live bar while a session runs), turned into directional
signals and the chart series the BI page draws."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import numpy as np

import market_data
from analytics import indicators as ind
from analytics import levels as lv
from common import last_valid, pct
from agents.base import AgentContext, fmt_pct, fmt_price, score_signals, section, signal, top_signals_text

AGENT = "technical"
WARMUP_DAYS = 700  # calendar days of extra history so SMA 200 / Ichimoku are warm at the chart's start


def _crossed(a: np.ndarray, b: np.ndarray, bars: int) -> str | None:
    """'up' if a crossed above b within the last `bars` bars, 'down' if below."""
    n = len(a)
    for i in range(n - 1, max(0, n - bars) - 1, -1):
        if i < 1 or np.isnan(a[i]) or np.isnan(b[i]) or np.isnan(a[i - 1]) or np.isnan(b[i - 1]):
            continue
        if a[i - 1] <= b[i - 1] and a[i] > b[i]:
            return "up"
        if a[i - 1] >= b[i - 1] and a[i] < b[i]:
            return "down"
    return None


def analyze(symbol: str, features: dict[str, dict[str, Any]], basis: str = "adjusted", lookback_days: int = 365,
            session: dict[str, Any] | None = None) -> dict[str, Any]:
    today = date.today()
    bars = market_data.daily_bars(symbol, basis, start=today - timedelta(days=lookback_days + WARMUP_DAYS))
    if len(bars) < 30:
        return section(AGENT, "no_data", summary=f"Not enough daily history for {symbol} ({len(bars)} sessions).",
                       features=list(features))
    o, h, l, c, v = bars.open, bars.high, bars.low, bars.close, bars.volume
    dates = bars.dates
    ws = bars.since(today - timedelta(days=lookback_days))
    last, prev = float(c[-1]), float(c[-2])
    sig: list[dict[str, Any]] = []
    overlays: dict[str, Any] = {}
    panels: dict[str, Any] = {}
    lines: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []

    year = bars.since(today - timedelta(days=365))
    hi52, lo52 = float(np.nanmax(h[year:])), float(np.nanmin(l[year:]))
    metrics: dict[str, Any] = {
        "last_close": last, "previous_close": prev, "change_pct": pct(last, prev), "basis": bars.basis,
        "last_date": dates[-1], "provisional_today": bars.provisional_today,
        "high_52w": hi52, "low_52w": lo52,
        "position_52w_pct": (last - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else None,
        "return_1m_pct": pct(last, float(c[bars.since(today - timedelta(days=30))])) if len(c) > 25 else None,
        "return_3m_pct": pct(last, float(c[bars.since(today - timedelta(days=91))])) if len(c) > 60 else None,
    }

    def win(a: np.ndarray) -> np.ndarray:
        return a[ws:]

    # --- moving averages
    for kind, fn, strength in (("sma", ind.sma, 0.35), ("ema", ind.ema, 0.25)):
        if kind not in features:
            continue
        for p in features[kind]["periods"]:
            ma = fn(c, p)
            val = last_valid(ma)
            overlays[f"{kind}_{p}"] = win(ma)
            if val is None:
                continue
            metrics[f"{kind}_{p}"] = val
            above = last > val
            w = strength * (1.4 if p >= 100 else 1.0)
            sig.append(signal(f"{kind}_{p}", f"Price {'above' if above else 'below'} {kind.upper()} {p}",
                              "bullish" if above else "bearish", w, val, f"{fmt_pct(pct(last, val))} from {kind.upper()} {p}"))

    if "trend_cross" in features:
        f = features["trend_cross"]
        fast, slow = ind.sma(c, f["fast"]), ind.sma(c, f["slow"])
        cross = _crossed(fast, slow, 10)
        if cross:
            name = "Golden cross" if cross == "up" else "Death cross"
            sig.append(signal("trend_cross", f"{name} (SMA {f['fast']}/{f['slow']}) in the last 10 sessions",
                              "bullish" if cross == "up" else "bearish", 0.8, weight=1.5))
        elif not np.isnan(fast[-1]) and not np.isnan(slow[-1]):
            up = fast[-1] > slow[-1]
            sig.append(signal("trend_cross", f"SMA {f['fast']} {'above' if up else 'below'} SMA {f['slow']}",
                              "bullish" if up else "bearish", 0.45, weight=1.5))
        overlays.setdefault(f"sma_{f['fast']}", win(fast))
        overlays.setdefault(f"sma_{f['slow']}", win(slow))

    if "bollinger" in features:
        f = features["bollinger"]
        bb = ind.bollinger(c, f["period"], f["std"])
        overlays["bb_upper"], overlays["bb_middle"], overlays["bb_lower"] = win(bb["upper"]), win(bb["middle"]), win(bb["lower"])
        pb, bw = last_valid(bb["percent_b"]), last_valid(bb["bandwidth"])
        metrics["bollinger_percent_b"] = pb
        metrics["bollinger_bandwidth"] = bw
        if pb is not None:
            if pb < 0:
                sig.append(signal("bollinger", "Close below the lower Bollinger band", "bullish", 0.5, pb, "stretched to the downside; mean-reversion setup"))
            elif pb > 1:
                sig.append(signal("bollinger", "Close above the upper Bollinger band", "bearish", 0.45, pb, "stretched to the upside"))
        bws = bb["bandwidth"][~np.isnan(bb["bandwidth"])][-120:]
        if bw is not None and bws.size > 60 and bw <= np.percentile(bws, 10):
            sig.append(signal("bollinger_squeeze", "Bollinger squeeze (bandwidth at a 6-month low)", "neutral", 0.4, bw,
                              "low volatility often precedes a breakout"))

    if "vwap" in features:
        vw = ind.rolling_vwap(h, l, c, v, features["vwap"]["period"])
        overlays["vwap"] = win(vw)
        val = last_valid(vw)
        if val:
            metrics["vwap"] = val
            sig.append(signal("vwap", f"Price {'above' if last > val else 'below'} {features['vwap']['period']}-session VWAP",
                              "bullish" if last > val else "bearish", 0.3, val))

    if "ichimoku" in features:
        f = features["ichimoku"]
        ich = ind.ichimoku(h, l, c, f["tenkan"], f["kijun"], f["senkou"])
        for k in ("tenkan", "kijun", "span_a", "span_b"):
            overlays[f"ichimoku_{k}"] = win(ich[k])
        a, b = ich["span_a"][-1], ich["span_b"][-1]
        if not np.isnan(a) and not np.isnan(b):
            top, bottom = max(a, b), min(a, b)
            if last > top:
                sig.append(signal("ichimoku", "Price above the Ichimoku cloud", "bullish", 0.6))
            elif last < bottom:
                sig.append(signal("ichimoku", "Price below the Ichimoku cloud", "bearish", 0.6))
            else:
                sig.append(signal("ichimoku", "Price inside the Ichimoku cloud", "neutral", 0.3))
            metrics["ichimoku_cloud_top"], metrics["ichimoku_cloud_bottom"] = top, bottom

    # --- oscillators
    if "rsi" in features:
        f = features["rsi"]
        r = ind.rsi(c, f["period"])
        panels["rsi"] = {"values": win(r), "overbought": f["overbought"], "oversold": f["oversold"], "period": f["period"]}
        val = last_valid(r)
        metrics["rsi"] = val
        if val is not None:
            crossed_up = _crossed(r, np.full(len(r), f["oversold"]), 3) == "up"
            crossed_down = _crossed(r, np.full(len(r), f["overbought"]), 3) == "down"
            if crossed_up:
                sig.append(signal("rsi", f"RSI crossed back above {f['oversold']:g}", "bullish", 0.7, val, "oversold reversal"))
            elif crossed_down:
                sig.append(signal("rsi", f"RSI fell back below {f['overbought']:g}", "bearish", 0.65, val, "overbought reversal"))
            elif val <= f["oversold"]:
                sig.append(signal("rsi", f"RSI oversold ({val:.0f})", "bullish", 0.55, val))
            elif val >= f["overbought"]:
                sig.append(signal("rsi", f"RSI overbought ({val:.0f})", "bearish", 0.55, val))
            else:
                sig.append(signal("rsi", f"RSI {val:.0f} ({'positive' if val >= 50 else 'negative'} momentum)",
                                  "bullish" if val >= 50 else "bearish", 0.2 + abs(val - 50) / 100, val))

    if "macd" in features:
        f = features["macd"]
        m = ind.macd(c, f["fast"], f["slow"], f["signal"])
        panels["macd"] = {"macd": win(m["macd"]), "signal": win(m["signal"]), "histogram": win(m["histogram"]),
                          "params": [f["fast"], f["slow"], f["signal"]]}
        line, sg, hist = last_valid(m["macd"]), last_valid(m["signal"]), last_valid(m["histogram"])
        metrics.update({"macd": line, "macd_signal": sg, "macd_histogram": hist})
        if line is not None and sg is not None:
            cross = _crossed(m["macd"], m["signal"], 3)
            hp = m["histogram"][~np.isnan(m["histogram"])]
            rising = hp.size >= 3 and hp[-1] > hp[-2] > hp[-3]
            if cross:
                sig.append(signal("macd", f"MACD {'bullish' if cross == 'up' else 'bearish'} crossover in the last 3 sessions",
                                  "bullish" if cross == "up" else "bearish", 0.7, line, weight=1.2))
            else:
                bull = line > sg
                sig.append(signal("macd", f"MACD {'above' if bull else 'below'} its signal line"
                                  f"{', histogram rising' if rising else ''}", "bullish" if bull else "bearish",
                                  0.4 + (0.1 if rising == bull else 0), line, weight=1.2))

    if "stochastic" in features:
        f = features["stochastic"]
        st = ind.stochastic(h, l, c, f["k"], f["d"], f["smooth"])
        panels["stochastic"] = {"k": win(st["k"]), "d": win(st["d"])}
        k, d = last_valid(st["k"]), last_valid(st["d"])
        metrics["stochastic_k"], metrics["stochastic_d"] = k, d
        if k is not None and d is not None:
            cross = _crossed(st["k"], st["d"], 3)
            if k < 20:
                sig.append(signal("stochastic", f"Stochastic oversold ({k:.0f}){', %K crossed above %D' if cross == 'up' else ''}",
                                  "bullish", 0.6 if cross == "up" else 0.35, k))
            elif k > 80:
                sig.append(signal("stochastic", f"Stochastic overbought ({k:.0f}){', %K crossed below %D' if cross == 'down' else ''}",
                                  "bearish", 0.6 if cross == "down" else 0.35, k))

    if "mfi" in features:
        val = last_valid(mf := ind.mfi(h, l, c, v, features["mfi"]["period"]))
        panels["mfi"] = {"values": win(mf)}
        metrics["mfi"] = val
        if val is not None and (val < 20 or val > 80):
            sig.append(signal("mfi", f"Money Flow Index {'oversold' if val < 20 else 'overbought'} ({val:.0f})",
                              "bullish" if val < 20 else "bearish", 0.45, val))

    if "cci" in features:
        val = last_valid(cc := ind.cci(h, l, c, features["cci"]["period"]))
        panels["cci"] = {"values": win(cc)}
        metrics["cci"] = val
        if val is not None and abs(val) > 100:
            sig.append(signal("cci", f"CCI {val:.0f} ({'oversold' if val < -100 else 'overbought'})",
                              "bullish" if val < -100 else "bearish", 0.35, val))

    if "williams_r" in features:
        val = last_valid(wr := ind.williams_r(h, l, c, features["williams_r"]["period"]))
        panels["williams_r"] = {"values": win(wr)}
        metrics["williams_r"] = val
        if val is not None and (val < -80 or val > -20):
            sig.append(signal("williams_r", f"Williams %R {val:.0f} ({'oversold' if val < -80 else 'overbought'})",
                              "bullish" if val < -80 else "bearish", 0.35, val))

    if "adx" in features:
        dm = ind.adx(h, l, c, features["adx"]["period"])
        panels["adx"] = {"adx": win(dm["adx"]), "plus_di": win(dm["plus_di"]), "minus_di": win(dm["minus_di"])}
        a, p_, m_ = last_valid(dm["adx"]), last_valid(dm["plus_di"]), last_valid(dm["minus_di"])
        metrics.update({"adx": a, "plus_di": p_, "minus_di": m_})
        if a is not None and p_ is not None and m_ is not None:
            if a >= 25:
                sig.append(signal("adx", f"Strong trend (ADX {a:.0f}), {'+DI' if p_ > m_ else '-DI'} leads",
                                  "bullish" if p_ > m_ else "bearish", min(0.8, 0.4 + (a - 25) / 50), a, weight=1.2))
            elif a < 20:
                sig.append(signal("adx", f"No clear trend (ADX {a:.0f})", "neutral", 0.3, a))

    if "atr" in features:
        at = ind.atr(h, l, c, features["atr"]["period"])
        panels["atr"] = {"values": win(at)}
        val = last_valid(at)
        metrics["atr"] = val
        metrics["atr_pct"] = val / last * 100 if val else None
        if val:
            metrics["stop_loss_2atr"] = last - 2 * val

    # --- volume
    if "volume" in features:
        p = features["volume"]["ma_period"]
        vma = ind.sma(v, p)
        overlays["volume_ma"] = win(vma)
        avg = last_valid(vma[:-1]) if len(vma) > 1 else None
        ratio = float(v[-1]) / avg if avg else None
        metrics.update({"volume": float(v[-1]), "volume_avg": avg, "volume_ratio": ratio})
        if ratio and ratio >= 1.8:
            up = last >= prev
            sig.append(signal("volume", f"Volume {ratio:.1f}x its {p}-session average on an {'up' if up else 'down'} day",
                              "bullish" if up else "bearish", min(0.7, 0.3 + ratio / 10), ratio))

    if "obv" in features:
        ob = ind.obv(c, v)
        panels["obv"] = {"values": win(ob)}
        s_obv, s_px = ind.slope(ob, 20), ind.slope(c, 20)
        metrics["obv_slope_20"] = s_obv
        if s_obv is not None and s_px is not None:
            if s_obv > 0 and s_px < 0:
                sig.append(signal("obv", "OBV rising while price falls (accumulation divergence)", "bullish", 0.45))
            elif s_obv < 0 and s_px > 0:
                sig.append(signal("obv", "OBV falling while price rises (distribution divergence)", "bearish", 0.45))
            else:
                sig.append(signal("obv", f"OBV trending {'up' if s_obv > 0 else 'down'} with price", "bullish" if s_obv > 0 else "bearish", 0.25))

    # --- levels and patterns
    if "support_resistance" in features:
        f = features["support_resistance"]
        sr = lv.support_resistance(h, l, c, f["lookback"], f["levels"])
        metrics["supports"], metrics["resistances"] = sr["supports"], sr["resistances"]
        for z in sr["supports"]:
            lines.append({"price": z["price"], "kind": "support", "label": f"S {z['price']:.1f} ({z['touches']}x)"})
        for z in sr["resistances"]:
            lines.append({"price": z["price"], "kind": "resistance", "label": f"R {z['price']:.1f} ({z['touches']}x)"})
        if sr["supports"] and abs(sr["supports"][0]["distance_pct"]) <= 2.5:
            sig.append(signal("support", f"Near support {fmt_price(sr['supports'][0]['price'])}", "bullish", 0.4,
                              sr["supports"][0]["price"], f"{fmt_pct(sr['supports'][0]['distance_pct'])} away"))
        if sr["resistances"] and abs(sr["resistances"][0]["distance_pct"]) <= 2.5:
            sig.append(signal("resistance", f"Near resistance {fmt_price(sr['resistances'][0]['price'])}", "bearish", 0.4,
                              sr["resistances"][0]["price"], f"{fmt_pct(sr['resistances'][0]['distance_pct'])} away"))

    if "fibonacci" in features:
        fib = lv.fibonacci(h, l, dates, features["fibonacci"]["lookback"])
        metrics["fibonacci"] = fib
        if fib:
            for lvl in fib["levels"]:
                lines.append({"price": lvl["price"], "kind": "fibonacci", "label": f"Fib {lvl['ratio'] * 100:.1f}%"})

    if "pivot_points" in features:
        i = -2 if bars.provisional_today and len(c) > 2 else -1
        metrics["pivot_points"] = lv.pivot_points(float(h[i]), float(l[i]), float(c[i]))
        metrics["pivot_points_from"] = dates[i]

    if "patterns" in features:
        pats = lv.candlestick_patterns(o, h, l, c, dates, features["patterns"]["recent"])
        metrics["patterns"] = pats
        for ptn in pats:
            markers.append({"date": ptn["date"], "label": ptn["pattern"], "direction": ptn["direction"]})
            if ptn["bars_ago"] <= 2 and ptn["direction"] != "neutral":
                sig.append(signal(f"pattern_{ptn['pattern'].lower().replace(' ', '_')}", f"{ptn['pattern']} ({ptn['bars_ago']} bars ago)",
                                  ptn["direction"], 0.4))

    for name in ("trend_cross", "macd"):
        pass  # crossovers are reflected in signals; markers come from patterns only

    charts: dict[str, Any] = {
        "dates": dates[ws:],
        "close": win(c),
        "candles": {"open": win(o), "high": win(h), "low": win(l), "close": win(c)} if "candlestick" in features else None,
        "volume": win(v) if "volume" in features else None,
        "overlays": overlays,
        "panels": panels,
        "lines": lines,
        "markers": markers,
        "basis": bars.basis,
        "provisional_today": bars.provisional_today,
    }
    if "intraday" in features:
        day = None
        if session and session.get("latest_scrape_trade_date"):
            day = date.fromisoformat(session["latest_scrape_trade_date"])
        path = market_data.intraday_path(symbol, day)
        charts["intraday"] = {"trade_date": day, "points": path} if path else None

    score = score_signals(sig)
    trend = "uptrend" if metrics.get("sma_200") and last > metrics["sma_200"] else "downtrend" if metrics.get("sma_200") else None
    parts = [f"{symbol} at {fmt_price(last)} ({fmt_pct(metrics['change_pct'])} vs. the previous session"
             f"{', live' if bars.provisional_today else ''}), {metrics['position_52w_pct']:.0f}% of its 52-week range"
             if metrics.get("position_52w_pct") is not None else f"{symbol} at {fmt_price(last)}"]
    if trend:
        parts.append(f"long-term {trend} (vs. SMA 200)")
    if metrics.get("rsi") is not None:
        parts.append(f"RSI {metrics['rsi']:.0f}")
    if sig:
        parts.append("key signals: " + top_signals_text(sig))
    if metrics.get("supports"):
        parts.append(f"support {fmt_price(metrics['supports'][0]['price'])}")
    if metrics.get("resistances"):
        parts.append(f"resistance {fmt_price(metrics['resistances'][0]['price'])}")
    summary = "; ".join(parts) + "."
    return section(AGENT, "ok", summary=summary, score=score, signals=sig, metrics=metrics, charts=charts,
                   features=list(features))


async def run(ctx: AgentContext) -> dict[str, Any]:
    return await asyncio.to_thread(
        analyze, ctx.symbol, ctx.features(AGENT), ctx.setting.get("price_basis", "adjusted"),
        int(ctx.setting.get("lookback_days") or 365), ctx.session,
    )
