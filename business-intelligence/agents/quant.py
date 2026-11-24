"""Quantitative agent: risk/return statistics of the adjusted daily log
returns -- volatility models (rolling, EWMA, GARCH(1,1)), drawdowns,
VaR/CVaR, beta vs. NEPSE, jump detection (the thesis' jump-diffusion
angle), Hurst / variance ratios, Monte Carlo and the volatility regime."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import numpy as np

import market_data
from analytics import statistics as st
from agents.base import AgentContext, score_signals, section, signal

AGENT = "quant"
HISTORY_DAYS = 365 * 6  # enough for 3-year regime percentiles and GARCH


def analyze(symbol: str, features: dict[str, dict[str, Any]], lookback_days: int) -> dict[str, Any]:
    today = date.today()
    bars = market_data.daily_bars(symbol, "adjusted", start=today - timedelta(days=HISTORY_DAYS))
    if len(bars) < 80:
        return section(AGENT, "no_data", summary=f"Not enough history for statistics ({len(bars)} sessions).", features=list(features))
    c = bars.close
    with np.errstate(divide="ignore", invalid="ignore"):
        r_all = np.diff(np.log(c))
    ok = np.isfinite(r_all)
    r = r_all[ok]
    r_dates = [d for d, good in zip(bars.dates[1:], ok) if good]
    ws = bars.since(today - timedelta(days=lookback_days))
    chart_dates = bars.dates[ws:]
    sig: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {"observations": int(r.size), "basis": bars.basis}
    charts: dict[str, Any] = {}
    data: dict[str, Any] = {}

    if "return_stats" in features:
        s = st.return_stats(r[-features["return_stats"]["window"]:])
        metrics["return_stats"] = s
        sharpe = s.get("sharpe")
        if sharpe is not None:
            if sharpe >= 1:
                sig.append(signal("sharpe", f"Strong risk-adjusted return (Sharpe {sharpe:.2f})", "bullish", min(0.6, 0.25 + sharpe / 5), sharpe))
            elif sharpe < 0:
                sig.append(signal("sharpe", f"Negative risk-adjusted return (Sharpe {sharpe:.2f})", "bearish", min(0.5, 0.2 + abs(sharpe) / 4), sharpe))

    if "volatility" in features:
        f = features["volatility"]
        rv = st.rolling_volatility(r, f["window"])
        charts["rolling_volatility"] = {"dates": r_dates[-len(chart_dates):], "values": (rv * 100)[-len(chart_dates):]}
        g = st.garch11(r[-1500:], f["forecast_days"])
        metrics["volatility"] = {"rolling_pct": float(rv[-1] * 100) if not np.isnan(rv[-1]) else None,
                                 "ewma_pct": (st.ewma_volatility(r) or 0) * 100 or None, "garch": g}
        if g and g.get("long_run_volatility_pct") and g["forecast_volatility_pct"] > 1.3 * g["long_run_volatility_pct"]:
            sig.append(signal("garch", f"GARCH expects elevated volatility ({g['forecast_volatility_pct']:.0f}% vs. long-run {g['long_run_volatility_pct']:.0f}%)",
                              "bearish", 0.3, g["forecast_volatility_pct"], "risk rising"))

    if "drawdown" in features:
        dd = st.drawdown(c, bars.dates)
        charts["drawdown"] = {"dates": chart_dates, "values": dd.pop("series")[ws:]}
        metrics["drawdown"] = dd
        cur = dd["current_drawdown_pct"]
        if cur <= -30:
            sig.append(signal("drawdown", f"{abs(cur):.0f}% below its all-period peak", "bearish", 0.3, cur, "long downtrend; also possible deep value"))
        elif cur >= -3:
            sig.append(signal("drawdown", "Trading near its peak", "bullish", 0.25, cur))

    if "var" in features:
        f = features["var"]
        v = st.value_at_risk(r[-720:], f["confidence"], f["horizon_days"])
        metrics["var"] = v
        if v and v["historical_var_pct"] >= 5 * (f["horizon_days"] ** 0.5):
            sig.append(signal("var", f"High tail risk: {f['confidence'] * 100:.0f}% VaR {v['historical_var_pct']:.1f}% over {f['horizon_days']} session(s)",
                              "bearish", 0.25, v["historical_var_pct"]))

    if "beta" in features:
        idx_dates, idx_close = market_data.index_closes("NEPSE", today - timedelta(days=HISTORY_DAYS))
        b = st.beta_vs_index(bars.dates, c, idx_dates, idx_close, features["beta"]["window"])
        metrics["beta"] = b
        if b:
            if b["beta"] >= 1.3:
                sig.append(signal("beta", f"High market sensitivity (beta {b['beta']:.2f})", "neutral", 0.3, b["beta"], "amplifies NEPSE moves both ways"))
            if b["alpha_annual_pct"] >= 10:
                sig.append(signal("alpha", f"Positive alpha vs. NEPSE ({b['alpha_annual_pct']:.0f}%/yr)", "bullish", 0.3, b["alpha_annual_pct"]))
            elif b["alpha_annual_pct"] <= -10:
                sig.append(signal("alpha", f"Negative alpha vs. NEPSE ({b['alpha_annual_pct']:.0f}%/yr)", "bearish", 0.3, b["alpha_annual_pct"]))

    if "jumps" in features:
        j = st.detect_jumps(r, r_dates, threshold=features["jumps"]["threshold"])
        metrics["jumps"] = {k: v for k, v in j.items() if k != "recent_jumps"}
        data["recent_jumps"] = j.get("recent_jumps", [])
        recent_down = [x for x in j.get("recent_jumps", []) if x["direction"] == "down" and x["date"] >= today - timedelta(days=90)]
        if recent_down:
            sig.append(signal("jumps", f"{len(recent_down)} downward price jump(s) in the last 3 months", "bearish", min(0.5, 0.25 + 0.1 * len(recent_down)),
                              len(recent_down), "jump risk (discontinuous moves) is elevated"))

    if "hurst" in features:
        h = st.hurst_exponent(r[-1000:])
        vrs = [v for v in (st.variance_ratio(r[-1000:], q) for q in (2, 5, 10)) if v]
        metrics["hurst"] = {"exponent": h, "variance_ratios": vrs,
                            "interpretation": None if h is None else "persistent (trending)" if h > 0.55 else "mean-reverting" if h < 0.45 else "random-walk-like"}

    if "monte_carlo" in features:
        f = features["monte_carlo"]
        raw_last = float(bars.raw_close[-1])
        mc = st.monte_carlo(raw_last, r, f["days"], f["paths"], f["method"])
        if mc:
            charts["monte_carlo"] = {"start_price": raw_last, "days": list(range(1, f["days"] + 1)), **mc.pop("percentiles")}
            metrics["monte_carlo"] = mc
            p = mc["probability_up_pct"]
            if p >= 60 or p <= 40:
                sig.append(signal("monte_carlo", f"{p:.0f}% of simulated paths end higher in {f['days']} sessions",
                                  "bullish" if p >= 60 else "bearish", 0.25, p, "historical drift; not a forecast"))

    if "regime" in features:
        reg = st.volatility_regime(r)
        metrics["regime"] = reg
        if reg and reg["regime"] in ("high", "extreme"):
            sig.append(signal("regime", f"{reg['regime'].title()} volatility regime ({reg['percentile']:.0f}th percentile of 3 years)",
                              "bearish", 0.4 if reg["regime"] == "extreme" else 0.3, reg["percentile"]))

    if "distribution" in features:
        charts["distribution"] = st.return_histogram(r[-720:])

    vol = (metrics.get("volatility") or {}).get("rolling_pct") or (metrics.get("return_stats") or {}).get("annual_volatility_pct")
    risk = None if vol is None else "low" if vol < 20 else "moderate" if vol < 35 else "high" if vol < 55 else "very high"
    metrics["risk_level"] = risk
    parts = []
    if vol is not None:
        parts.append(f"annualised volatility {vol:.0f}% ({risk} risk)")
    rs = metrics.get("return_stats") or {}
    if rs.get("sharpe") is not None:
        parts.append(f"Sharpe {rs['sharpe']:.2f}")
    if metrics.get("beta"):
        parts.append(f"beta {metrics['beta']['beta']:.2f} vs. NEPSE")
    if metrics.get("drawdown"):
        parts.append(f"{metrics['drawdown']['current_drawdown_pct']:.0f}% from peak (max {metrics['drawdown']['max_drawdown_pct']:.0f}%)")
    if metrics.get("var"):
        v = metrics["var"]
        parts.append(f"{v['confidence'] * 100:.0f}% {v['horizon_days']}-session VaR {v['historical_var_pct']:.1f}%")
    if metrics.get("regime"):
        parts.append(f"{metrics['regime']['regime']} volatility regime")
    return section(AGENT, "ok", summary="; ".join(parts) + "." if parts else "", score=score_signals(sig), signals=sig,
                   metrics=metrics, charts=charts, data=data, features=list(features))


async def run(ctx: AgentContext) -> dict[str, Any]:
    return await asyncio.to_thread(analyze, ctx.symbol, ctx.features(AGENT), int(ctx.setting.get("lookback_days") or 365))
