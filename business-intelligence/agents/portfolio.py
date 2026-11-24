"""Portfolio agent: given a budget, a time horizon and a target return, find
the lowest-risk combination of NEPSE scripts expected to reach that return
(mean-variance optimisation on the analytics), turn it into whole-lot share
orders, and analyse its risk.

Expected returns, per script (annual, log):
  historical mean of 2 years of adjusted daily returns, shrunk 50% toward
  the universe average (raw means are very noisy), plus a tilt from the
  analytics: kappa * (score / 100) * volatility, where score (-100..100) is
  the script's BI report score when one is fresh, otherwise a quick screen
  (momentum, trend, RSI, valuation vs. sector, dividend yield).
Covariance: sample covariance with Ledoit-Wolf shrinkage to a scaled identity.
Both are scaled to the horizon; buying costs (cost_pct per side) are netted.

Optimisation (scipy SLSQP, long-only, per-script cap, cash allowed):
  minimise variance subject to expected return >= target. When the target
  is above what the caps allow, the maximum-return portfolio is returned and
  the shortfall reported. Max-Sharpe and min-variance portfolios and the
  efficient frontier are returned for comparison.

Risk analysis: horizon volatility, probability of reaching the target and of
a loss, VaR/CVaR (block-bootstrap Monte Carlo of the joint daily returns,
re-centred on the expected drift), expected max drawdown, a 1-year
historical replay, beta to NEPSE and a -10% NEPSE shock, risk contribution
and liquidity (days to build each position at 10% of its daily turnover).
"""
from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import numpy as np
from scipy import optimize
from sqlalchemy import text

import market_data
import store
from analytics import indicators as ind
from common import clean, now_npt

TRADING_DAYS = 240
HORIZONS = {"1M": 20, "3M": 60, "6M": 120, "1Y": 240}
KAPPA = 0.5
SHRINK = 0.5
DEFAULT_MAX_WEIGHT = {"conservative": 20.0, "moderate": 25.0, "aggressive": 35.0}
DEFAULT_MAX_SECTOR = {"conservative": 35.0, "moderate": 50.0, "aggressive": 70.0}

Progress = Callable[[str, str, float], None]


# ------------------------------------------------------------------ request


def validate_request(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise the dashboard's request; raises ValueError (shown to the user)."""
    try:
        budget = float(raw.get("budget"))
    except (TypeError, ValueError):
        raise ValueError("budget must be a number (NPR)")
    if not 5_000 <= budget <= 10_000_000_000:
        raise ValueError("budget must be between NPR 5,000 and 10 billion")
    horizon = str(raw.get("horizon") or "3M").upper()
    if horizon not in HORIZONS:
        raise ValueError(f"horizon must be one of {', '.join(HORIZONS)}")
    try:
        target = float(raw.get("target_return_pct", 10))
    except (TypeError, ValueError):
        raise ValueError("target_return_pct must be a number")
    if not -20 <= target <= 300:
        raise ValueError("target return must be between -20% and 300%")
    risk = raw.get("risk_profile") or "moderate"
    if risk not in DEFAULT_MAX_WEIGHT:
        raise ValueError("risk_profile must be conservative, moderate or aggressive")
    universe = raw.get("universe") or "liquid"
    if universe not in ("liquid", "bi"):
        raise ValueError("universe must be 'liquid' (most traded + BI scripts) or 'bi' (BI scripts only)")
    size = int(raw.get("universe_size") or 40)
    max_w = float(raw.get("max_weight_pct") or DEFAULT_MAX_WEIGHT[risk])
    max_sector = float(raw.get("max_sector_pct") or DEFAULT_MAX_SECTOR[risk])
    lot = int(raw.get("lot_size") or 10)
    cost = float(raw.get("cost_pct") if raw.get("cost_pct") is not None else 0.45)
    if not 10 <= size <= 80:
        raise ValueError("universe_size must be 10-80")
    if not 5 <= max_w <= 100:
        raise ValueError("max_weight_pct must be 5-100")
    if not 10 <= max_sector <= 100:
        raise ValueError("max_sector_pct must be 10-100")
    if not 1 <= lot <= 100:
        raise ValueError("lot_size must be 1-100")
    if not 0 <= cost <= 3:
        raise ValueError("cost_pct must be 0-3")
    holdings = []
    for h in raw.get("holdings") or []:
        sym = str(h.get("symbol") or "").strip().upper()
        qty = int(float(h.get("quantity") or 0))
        if sym and qty > 0:
            holdings.append({"symbol": sym, "quantity": qty})
    exclude = sorted({str(s).strip().upper() for s in raw.get("exclude") or [] if str(s).strip()})
    return {"budget": budget, "horizon": horizon, "target_return_pct": target, "risk_profile": risk, "universe": universe,
            "universe_size": size, "max_weight_pct": max_w, "max_sector_pct": max_sector, "lot_size": lot, "cost_pct": cost, "holdings": holdings[:50],
            "exclude": exclude[:50]}


# ------------------------------------------------------------------ data


def _universe(req: dict[str, Any]) -> tuple[list[str], dict[str, float]]:
    """Candidate scripts and their average daily turnover (last ~60 sessions)."""
    configured = [s["symbol"] for s in store.list_settings() if s["enabled"]]
    with market_data._session() as s:
        rows = s.execute(
            text(
                """
                SELECT d.symbol, avg(d.turnover) AS turnover
                FROM market_stock_daily d
                JOIN (SELECT DISTINCT symbol FROM market_security WHERE listing_status = 'A' AND instrument_type = 'Equity') ms
                  ON ms.symbol = d.symbol
                WHERE d.trade_date >= current_date - 90
                GROUP BY d.symbol HAVING count(*) >= 30 AND max(d.trade_date) >= current_date - 10
                ORDER BY 2 DESC NULLS LAST
                """
            )
        ).all()
    turnover = {r.symbol: float(r.turnover or 0) for r in rows}
    if req["universe"] == "bi":
        cands = list(configured)
    else:
        cands = list(dict.fromkeys(configured + [r.symbol for r in rows[: req["universe_size"]]]))
    cands = list(dict.fromkeys(cands + [h["symbol"] for h in req["holdings"]]))
    return [c for c in cands if c not in req["exclude"]], turnover


def _price_matrix(symbols: list[str], years: float = 2.0) -> tuple[list[date], np.ndarray, list[str]]:
    """Adjusted closes on the NEPSE trading calendar, forward-filled over
    sessions a script didn't trade; scripts with too little history dropped."""
    start = date.today() - timedelta(days=int(365 * years) + 10)
    cal, _ = market_data.index_closes("NEPSE", start)
    series = market_data.adjusted_closes_many(symbols, start)
    pos = {d: i for i, d in enumerate(cal)}
    kept, cols = [], []
    for s in symbols:
        if s not in series:
            continue
        d, c = series[s]
        col = np.full(len(cal), np.nan)
        for di, ci in zip(d, c):
            if di in pos:
                col[pos[di]] = ci
        filled = int(np.sum(~np.isnan(col)))
        if filled < 0.5 * len(cal) or filled < 150:
            continue
        last = np.nan
        for i in range(len(col)):  # forward fill
            last = col[i] if not np.isnan(col[i]) else last
            col[i] = last
        kept.append(s)
        cols.append(col)
    if not cols:
        return cal, np.empty((len(cal), 0)), []
    m = np.column_stack(cols)
    first = int(np.argmax(~np.isnan(m).any(axis=1)))  # first row where every kept script has a price
    return cal[first:], m[first:], kept


def _quick_scores(symbols: list[str], prices: np.ndarray) -> dict[str, dict[str, Any]]:
    """Analytics score for scripts without a fresh BI report: momentum (6M,
    z-scored across the universe), trend (SMA 200 / 50), RSI extremes,
    valuation vs. sector median P/E and dividend yield."""
    n = prices.shape[0]
    mom = np.array([prices[-1, j] / prices[max(0, n - 120), j] - 1 for j in range(len(symbols))])
    z = (mom - mom.mean()) / (mom.std() or 1)
    with market_data._session() as s:
        fund = {r.symbol: r for r in s.execute(text(
            """
            SELECT DISTINCT ON (f.symbol) f.symbol, f.pe_ratio, f.cash_dividend_pct, f.market_price, f.paidup_value, ms.sector_name
            FROM market_fundamental_daily f
            LEFT JOIN (SELECT DISTINCT ON (symbol) symbol, sector_name FROM market_security ORDER BY symbol, (listing_status = 'A') DESC) ms
              ON ms.symbol = f.symbol
            WHERE f.trade_date >= current_date - 10 ORDER BY f.symbol, f.trade_date DESC
            """)).all()}
    sector_pe: dict[str, list[float]] = {}
    for r in fund.values():
        if r.pe_ratio and 0 < r.pe_ratio < 200 and r.sector_name:
            sector_pe.setdefault(r.sector_name, []).append(r.pe_ratio)
    out = {}
    for j, sym in enumerate(symbols):
        c = prices[:, j]
        parts: list[tuple[str, float]] = [("6-month momentum", float(np.clip(z[j] * 20, -40, 40)))]
        sma200, sma50 = ind.sma(c, 200)[-1], ind.sma(c, 50)[-1]
        if not np.isnan(sma200):
            parts.append(("price vs. SMA 200", 25.0 if c[-1] > sma200 else -25.0))
            if not np.isnan(sma50):
                parts.append(("SMA 50 vs. SMA 200", 15.0 if sma50 > sma200 else -15.0))
        rsi = ind.rsi(c, 14)[-1]
        if not np.isnan(rsi):
            if rsi > 75:
                parts.append((f"RSI overbought ({rsi:.0f})", -10.0))
            elif rsi < 30:
                parts.append((f"RSI oversold ({rsi:.0f})", 10.0))
        f = fund.get(sym)
        if f is not None:
            peers = sector_pe.get(f.sector_name or "", [])
            if f.pe_ratio and peers and len(peers) >= 3:
                med = float(np.median(peers))
                rel = f.pe_ratio / med - 1
                if rel <= -0.2:
                    parts.append((f"P/E {f.pe_ratio:.1f} below sector median {med:.1f}", 15.0))
                elif rel >= 0.3:
                    parts.append((f"P/E {f.pe_ratio:.1f} above sector median {med:.1f}", -15.0))
            if f.cash_dividend_pct and f.market_price:
                dy = f.cash_dividend_pct * (f.paidup_value or 100) / f.market_price
                if dy >= 4:
                    parts.append((f"dividend yield {dy:.1f}%", 5.0))
        score = float(np.clip(sum(v for _, v in parts), -100, 100))
        out[sym] = {"score": score, "source": "quick screen", "factors": [f"{k} ({v:+.0f})" for k, v in parts if v]}
    return out


def _ledoit_wolf(x: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf shrinkage of the sample covariance toward mu*I."""
    t, n = x.shape
    xc = x - x.mean(axis=0)
    s = xc.T @ xc / t
    mu = np.trace(s) / n
    f = mu * np.eye(n)
    d2 = np.sum((s - f) ** 2)
    b2 = sum(np.sum((np.outer(r, r) - s) ** 2) for r in xc) / t ** 2
    shrink = min(1.0, b2 / d2) if d2 > 0 else 1.0
    return shrink * f + (1 - shrink) * s


# ------------------------------------------------------------------ optimisation


def _solve(mu: np.ndarray, cov: np.ndarray, cap: float, *, target: float | None = None, objective: str = "min_var",
           groups: list[np.ndarray] | None = None, group_cap: float = 1.0) -> np.ndarray | None:
    n = mu.size
    bounds = [(0.0, cap)] * n
    sector_cons = [{"type": "ineq", "fun": lambda w, g=g: group_cap - w[g].sum()} for g in (groups or []) if g.size > 1]
    cons = [{"type": "ineq", "fun": lambda w: 1.0 - w.sum()}]  # the rest stays in cash
    if objective == "max_sharpe":
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        fun = lambda w: -(mu @ w) / math.sqrt(max(w @ cov @ w, 1e-12))  # noqa: E731
    elif objective == "max_return":
        fun = lambda w: -(mu @ w) + 1e-3 * (w @ cov @ w)  # noqa: E731
    else:
        fun = lambda w: w @ cov @ w  # noqa: E731
        if target is not None:
            cons.append({"type": "ineq", "fun": lambda w: mu @ w - target})
        else:
            cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    if objective in ("max_sharpe",) or (objective == "min_var" and target is None):
        if cap * n < 1:
            return None
    cons = cons + sector_cons
    best = None
    for start in (np.full(n, min(cap, 1.0 / n)), np.clip(mu.clip(0) / (mu.clip(0).sum() or 1), 0, cap)):
        res = optimize.minimize(fun, start, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 500, "ftol": 1e-12})
        if res.success and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        return None
    w = np.clip(best.x, 0, cap)
    w[w < 1e-4] = 0
    return w


def _max_return(mu: np.ndarray, cap: float, sector_of: list[str], group_cap: float) -> tuple[np.ndarray, float]:
    """Highest expected return under the script and sector caps (greedy fill:
    the LP optimum when every script's cap is equal)."""
    w = np.zeros(mu.size)
    left = 1.0
    used: dict[str, float] = {}
    for i in np.argsort(-mu):
        if mu[i] <= 0 or left <= 1e-9:
            break
        room = group_cap - used.get(sector_of[i], 0.0)
        w[i] = max(0.0, min(cap, left, room))
        used[sector_of[i]] = used.get(sector_of[i], 0.0) + w[i]
        left -= w[i]
    return w, float(mu @ w)


def _stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> dict[str, float]:
    ret, vol = float(mu @ w), math.sqrt(max(float(w @ cov @ w), 0.0))
    return {"expected_return_pct": ret * 100, "volatility_pct": vol * 100, "sharpe": ret / vol if vol > 0 else None,
            "invested_pct": float(w.sum() * 100)}


# ------------------------------------------------------------------ main


def optimize_portfolio(req: dict[str, Any], progress: Progress) -> dict[str, Any]:
    h = HORIZONS[req["horizon"]]
    scale = h / TRADING_DAYS
    target = req["target_return_pct"] / 100.0
    cap = req["max_weight_pct"] / 100.0
    cost = req["cost_pct"] / 100.0

    progress("universe", "Selecting candidate scripts", 0.05)
    symbols, turnover = _universe(req)
    if len(symbols) < 2:
        raise ValueError("Not enough candidate scripts: set up more scripts on the BI Setup page or use the 'liquid' universe.")

    progress("data", f"Loading 2 years of adjusted prices for {len(symbols)} scripts", 0.15)
    dates, prices, kept = _price_matrix(symbols)
    dropped = [s for s in symbols if s not in kept]
    if len(kept) < 2:
        raise ValueError("Not enough price history for the candidate scripts.")
    rets = np.diff(np.log(prices), axis=0)
    n = len(kept)

    progress("signals", "Scoring scripts from the BI reports and a quick analytics screen", 0.3)
    info = market_data.securities_info(kept)
    quick = _quick_scores(kept, prices)
    scores: dict[str, dict[str, Any]] = {}
    for sym in kept:
        rep = store.get_report(sym)
        fresh = rep and rep.get("generated_at") and str(rep["generated_at"]) >= (now_npt() - timedelta(days=3)).isoformat()
        if fresh and rep.get("score") is not None:
            syn = rep.get("synthesis") or {}
            scores[sym] = {"score": float(rep["score"]), "source": "BI report", "recommendation": rep.get("recommendation"),
                           "factors": (syn.get("bullish_factors") or [])[:2] + (syn.get("bearish_factors") or [])[:2]}
        else:
            scores[sym] = quick[sym]
    s_vec = np.array([scores[s]["score"] for s in kept]) / 100.0

    progress("model", "Estimating expected returns and covariance", 0.45)
    mu_hist = rets.mean(axis=0) * TRADING_DAYS
    cov_annual = _ledoit_wolf(rets) * TRADING_DAYS
    sigma = np.sqrt(np.diag(cov_annual))
    mu_shrunk = SHRINK * mu_hist + (1 - SHRINK) * mu_hist.mean()
    mu_annual = mu_shrunk + KAPPA * s_vec * sigma
    held = {hd["symbol"]: hd["quantity"] for hd in req["holdings"]}
    entry_cost = np.array([cost if s in held else 2 * cost for s in kept])  # new buys pay both sides
    mu_h = (mu_annual + 0.5 * sigma ** 2) * scale - entry_cost  # simple-return approximation, net of costs
    cov_h = cov_annual * scale

    progress("optimize", "Optimising the allocation for your target return", 0.6)
    sector_of = [(info.get(s) or {}).get("sector_name") or "Other" for s in kept]
    groups = [np.array([j for j in range(n) if sector_of[j] == sec]) for sec in sorted(set(sector_of))]
    gcap = req["max_sector_pct"] / 100.0
    w_max, max_ret = _max_return(mu_h, cap, sector_of, gcap)
    target_reachable = target <= max_ret
    if target <= 0:
        w = _solve(mu_h, cov_h, cap, target=target, groups=groups, group_cap=gcap) if target > -1 else np.zeros(n)
        w = w if w is not None else np.zeros(n)
        mode = "target (low)"
    elif target_reachable:
        w = _solve(mu_h, cov_h, cap, target=target, groups=groups, group_cap=gcap)
        mode = "min risk for target"
        if w is None or float(mu_h @ w) < target - 1e-3:
            w, mode = w_max, "max return (solver fallback)"
    else:
        w, mode = w_max, "max return (target not reachable)"
    # Drop crumbs (< 2% of capital): re-solve on the survivors and keep that
    # only if it still meets the target.
    keep = w >= 0.02
    if mode == "min risk for target" and 1 <= keep.sum() < (w > 0).sum():
        kidx = np.flatnonzero(keep)
        sub_groups = [np.array([k for k, j in enumerate(kidx) if sector_of[j] == sec]) for sec in sorted({sector_of[j] for j in kidx})]
        sub = _solve(mu_h[keep], cov_h[np.ix_(keep, keep)], cap, target=target, groups=sub_groups, group_cap=gcap)
        if sub is not None and float(mu_h[keep] @ sub) >= target - 1e-3:
            w = np.zeros(n)
            w[keep] = sub
    elif mode != "min risk for target":
        w = np.where(keep, w, 0)
    w_ms = _solve(mu_h, cov_h, cap, objective="max_sharpe", groups=groups, group_cap=gcap)
    w_mv = _solve(mu_h, cov_h, cap, groups=groups, group_cap=gcap)
    frontier = []
    lo = float(mu_h @ w_mv) if w_mv is not None else 0.0
    for t in np.linspace(lo, max_ret, 12) if max_ret > lo else []:
        wf = _solve(mu_h, cov_h, cap, target=float(t), groups=groups, group_cap=gcap)
        if wf is not None:
            frontier.append({"return_pct": float(mu_h @ wf) * 100, "volatility_pct": math.sqrt(max(float(wf @ cov_h @ wf), 0)) * 100})

    progress("allocation", "Converting weights into whole-lot share orders", 0.72)
    last_raw = {}
    for s in kept:
        q = market_data.live_quote(s)
        last_raw[s] = float(q["last_traded_price"]) if q and q.get("last_traded_price") else None
    for j, s in enumerate(kept):
        if last_raw[s] is None:
            bars = market_data.daily_bars(s, "raw", start=date.today() - timedelta(days=20), include_live=False)
            last_raw[s] = float(bars.close[-1]) if len(bars) else float("nan")
    holdings_value = sum(held.get(s, 0) * (last_raw.get(s) or 0) for s in held)
    capital = req["budget"] + holdings_value
    lot = req["lot_size"]
    shares = {s: int((w[j] * capital) // (last_raw[s] * lot) * lot) if last_raw[s] and w[j] > 0 else 0 for j, s in enumerate(kept)}
    spent = sum(shares[s] * last_raw[s] for s in kept)
    # Spend the rounding leftovers on the best-scoring held weights, a lot at a time.
    order = sorted((j for j in range(n) if w[j] > 0), key=lambda j: -mu_h[j])
    changed = True
    while changed:
        changed = False
        for j in order:
            s = kept[j]
            add = lot * last_raw[s]
            if spent + add <= capital and (shares[s] + lot) * last_raw[s] <= (cap + 0.02) * capital:
                shares[s] += lot
                spent += add
                changed = True
    w_real = np.array([shares[s] * last_raw[s] / capital for s in kept])

    progress("risk", "Running the risk analysis (Monte Carlo, VaR, drawdown, stress)", 0.82)
    risk = _risk_analysis(w_real, kept, dates, prices, rets, mu_h, cov_h, h, target, capital, info, turnover, last_raw, shares)

    allocations = []
    for j, s in enumerate(kept):
        cur = held.get(s, 0)
        if shares[s] == 0 and cur == 0:
            continue
        diff = shares[s] - cur
        action = "buy" if cur == 0 and diff > 0 else "sell" if shares[s] == 0 else "increase" if diff > 0 else "reduce" if diff < 0 else "hold"
        allocations.append({
            "symbol": s, "company": (info.get(s) or {}).get("company_name"), "sector": (info.get(s) or {}).get("sector_name"),
            "weight_pct": w_real[j] * 100, "target_weight_pct": w[j] * 100, "price": last_raw[s], "shares": shares[s],
            "amount": shares[s] * last_raw[s], "current_shares": cur, "trade_shares": diff, "action": action,
            "expected_return_pct": mu_h[j] * 100, "volatility_pct": math.sqrt(cov_h[j, j]) * 100,
            "score": scores[s]["score"], "score_source": scores[s]["source"], "recommendation": scores[s].get("recommendation"),
            "factors": scores[s]["factors"], "risk_contribution_pct": risk["risk_contribution"].get(s),
            "days_to_build": risk["liquidity_days"].get(s),
        })
    allocations.sort(key=lambda a: -a["amount"])
    sells = [{"symbol": s, "shares": q, "reason": "excluded or no usable price history: review manually"}
             for s, q in held.items() if s not in kept]
    buy_value = sum(max(a["trade_shares"], 0) * a["price"] for a in allocations)
    sell_value = sum(max(-a["trade_shares"], 0) * a["price"] for a in allocations)
    port = {**_stats(w_real, mu_h, cov_h), **risk["summary"], "capital": capital, "budget": req["budget"], "holdings_value": holdings_value,
            "invested": spent, "cash_left": capital - spent, "expected_profit": capital * float(mu_h @ w_real),
            "estimated_fees": (buy_value + sell_value) * cost, "positions": sum(1 for a in allocations if a["shares"] > 0),
            "target_return_pct": req["target_return_pct"], "target_reachable": target_reachable,
            "max_achievable_return_pct": max_ret * 100, "mode": mode}

    alternatives = {}
    for name, wa in (("max_sharpe", w_ms), ("min_variance", w_mv), ("max_return", w_max)):
        if wa is not None:
            alternatives[name] = {**_stats(wa, mu_h, cov_h),
                                  "weights": sorted(({"symbol": kept[j], "weight_pct": wa[j] * 100} for j in range(n) if wa[j] > 0.005),
                                                    key=lambda x: -x["weight_pct"])[:12]}
    return clean({
        "request": req, "generated_at": now_npt(), "as_of": dates[-1], "horizon_sessions": h,
        "universe": {"considered": len(symbols), "modelled": n, "dropped_for_history": dropped},
        "assumptions": {"history_years": 2, "expected_return": f"50% shrunk historical mean + {KAPPA} x score/100 x volatility",
                        "covariance": "Ledoit-Wolf shrinkage", "cost_pct_per_side": req["cost_pct"], "lot_size": lot,
                        "max_weight_pct": req["max_weight_pct"], "max_sector_pct": req["max_sector_pct"], "trading_days_per_year": TRADING_DAYS},
        "portfolio": port, "allocations": allocations, "sells": sells, "alternatives": alternatives,
        "frontier": frontier, "chosen_point": {"return_pct": port["expected_return_pct"], "volatility_pct": port["volatility_pct"]},
        "sector_exposure": risk["sectors"], "risk": {k: v for k, v in risk.items() if k not in ("summary", "risk_contribution", "liquidity_days", "sectors")},
    })


def _risk_analysis(w: np.ndarray, syms: list[str], dates: list[date], prices: np.ndarray, rets: np.ndarray, mu_h: np.ndarray,
                   cov_h: np.ndarray, h: int, target: float, capital: float, info: dict[str, Any], turnover: dict[str, float],
                   last_raw: dict[str, float], shares: dict[str, int]) -> dict[str, Any]:
    rng = np.random.default_rng(11)
    invested = float(w.sum())
    port_daily = rets @ w
    # Block bootstrap (5-session blocks keep short-term dependence), re-centred
    # so the simulated mean equals the model's expected return.
    paths, block = 4000, 5
    nblocks = math.ceil(h / block)
    starts = rng.integers(0, max(1, port_daily.size - block), size=(paths, nblocks))
    sims = np.stack([port_daily[s:s + block] for s in starts.ravel()]).reshape(paths, nblocks * block)[:, :h]
    sims = sims - port_daily.mean() + (float(mu_h @ w) / h if h else 0)
    cum = np.cumsum(sims, axis=1)
    final = np.expm1(cum[:, -1])
    peak = np.maximum.accumulate(np.concatenate([np.zeros((paths, 1)), cum], axis=1), axis=1)[:, 1:]
    mdd = np.expm1(cum - peak).min(axis=1)
    q5 = float(np.quantile(final, 0.05))
    cvar = float(final[final <= q5].mean()) if (final <= q5).any() else q5

    # Historical replay of the same weights over the last year (buy and hold proportions).
    last_year = port_daily[-TRADING_DAYS:]
    hist_cum = np.expm1(np.cumsum(last_year))
    hist_mdd = float(np.min(np.expm1(np.cumsum(last_year) - np.maximum.accumulate(np.concatenate([[0], np.cumsum(last_year)]))[1:])))
    windows = np.convolve(port_daily, np.ones(h), "valid") if port_daily.size >= h else np.array([])

    # Beta to NEPSE and a -10% index shock.
    idx_dates, idx_close = market_data.index_closes("NEPSE", dates[0])
    idx = {d: v for d, v in zip(idx_dates, idx_close)}
    m = np.array([idx.get(d, np.nan) for d in dates])
    m_ret = np.diff(np.log(m))
    ok = np.isfinite(m_ret)
    beta = float(np.cov(port_daily[ok], m_ret[ok], ddof=1)[0, 1] / np.var(m_ret[ok], ddof=1)) if ok.sum() > 30 and invested > 0 else 0.0

    total_var = float(w @ cov_h @ w)
    contrib = {syms[j]: float(w[j] * (cov_h @ w)[j] / total_var * 100) for j in range(len(syms)) if w[j] > 0 and total_var > 0}
    liquidity = {s: (shares[s] * last_raw[s]) / (0.1 * turnover[s]) for s in syms if shares.get(s) and turnover.get(s)}
    sectors: dict[str, float] = {}
    for j, s in enumerate(syms):
        if w[j] > 0:
            sec = (info.get(s) or {}).get("sector_name") or "Other"
            sectors[sec] = sectors.get(sec, 0) + float(w[j] * 100)
    corr = np.corrcoef(rets[:, w > 0].T) if (w > 0).sum() > 1 else None
    avg_corr = float((corr.sum() - corr.shape[0]) / (corr.shape[0] * (corr.shape[0] - 1))) if corr is not None else None
    hist = np.histogram(final * 100, bins=30)
    return {
        "summary": {
            "probability_reach_target_pct": float((final >= target).mean() * 100),
            "probability_loss_pct": float((final < 0).mean() * 100),
            "var_95_pct": -q5 * 100, "cvar_95_pct": -cvar * 100,
            "var_95_amount": -q5 * capital, "cvar_95_amount": -cvar * capital,
            "expected_max_drawdown_pct": float(np.median(mdd) * 100), "bad_case_max_drawdown_pct": float(np.quantile(mdd, 0.05) * 100),
            "beta_nepse": beta, "nepse_minus_10_impact_pct": beta * -10 * invested,
            "effective_positions": float(1 / np.sum((w[w > 0] / w.sum()) ** 2)) if invested > 0 else 0,
            "average_correlation": avg_corr,
        },
        "outcome_percentiles_pct": {f"p{p}": float(np.quantile(final, p / 100) * 100) for p in (5, 25, 50, 75, 95)},
        "outcome_histogram": {"centers": ((hist[1][:-1] + hist[1][1:]) / 2).tolist(), "counts": hist[0].tolist()},
        "simulated_paths_pct": {f"p{p}": (np.expm1(np.quantile(cum, p / 100, axis=0)) * 100).tolist() for p in (5, 25, 50, 75, 95)},
        "historical_replay": {"dates": dates[-len(last_year):], "cumulative_pct": (hist_cum * 100).tolist(), "return_pct": float(hist_cum[-1] * 100) if hist_cum.size else None,
                              "max_drawdown_pct": hist_mdd * 100,
                              "worst_window_pct": float(np.expm1(windows.min()) * 100) if windows.size else None,
                              "best_window_pct": float(np.expm1(windows.max()) * 100) if windows.size else None},
        "risk_contribution": contrib, "liquidity_days": liquidity,
        "sectors": sorted(({"sector": k, "weight_pct": v} for k, v in sectors.items()), key=lambda x: -x["weight_pct"]),
    }
