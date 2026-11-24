"""Quantitative / statistical analysis of a daily price series.

Inputs are adjusted closes (no artificial ex-date drops). Annualisation
uses TRADING_DAYS sessions per year (NEPSE: ~230-240 sessions; 240 is used).
Risk-free rate defaults to 0: NEPSE has no liquid benchmark rate series in
this database.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
from scipy import optimize, stats

TRADING_DAYS = 240


def log_returns(close: np.ndarray) -> np.ndarray:
    c = np.asarray(close, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.diff(np.log(c))
    return r[np.isfinite(r)]


def return_stats(r: np.ndarray, risk_free: float = 0.0) -> dict[str, Any]:
    if r.size < 20:
        return {}
    mean_d, sd_d = float(r.mean()), float(r.std(ddof=1))
    downside = r[r < 0]
    dsd = float(np.sqrt(np.mean(np.square(downside)))) if downside.size else 0.0
    ann_ret = mean_d * TRADING_DAYS
    ann_vol = sd_d * math.sqrt(TRADING_DAYS)
    return {
        "observations": int(r.size),
        "annual_return_pct": (math.exp(ann_ret) - 1) * 100,
        "annual_volatility_pct": ann_vol * 100,
        "sharpe": (ann_ret - risk_free) / ann_vol if ann_vol else None,
        "sortino": (ann_ret - risk_free) / (dsd * math.sqrt(TRADING_DAYS)) if dsd else None,
        "skewness": float(stats.skew(r)),
        "excess_kurtosis": float(stats.kurtosis(r)),
        "best_day_pct": (math.exp(float(r.max())) - 1) * 100,
        "worst_day_pct": (math.exp(float(r.min())) - 1) * 100,
        "positive_days_pct": float((r > 0).mean() * 100),
        "jarque_bera_p": float(stats.jarque_bera(r).pvalue),
    }


def rolling_volatility(r: np.ndarray, window: int = 20) -> np.ndarray:
    """Annualised rolling std of log returns (NaN until `window` returns)."""
    out = np.full(r.size, np.nan)
    for i in range(window - 1, r.size):
        out[i] = r[i - window + 1:i + 1].std(ddof=1) * math.sqrt(TRADING_DAYS)
    return out


def ewma_volatility(r: np.ndarray, lam: float = 0.94) -> float | None:
    if r.size < 30:
        return None
    var = float(np.var(r[:30]))
    for x in r[30:]:
        var = lam * var + (1 - lam) * x * x
    return math.sqrt(var * TRADING_DAYS)


def garch11(r: np.ndarray, horizon: int = 10) -> dict[str, Any] | None:
    """GARCH(1,1) with normal innovations, fitted by maximum likelihood on
    demeaned returns. Returns the parameters, persistence (alpha+beta), the
    variance half-life and an annualised volatility forecast `horizon`
    sessions ahead."""
    if r.size < 250:
        return None
    x = r - r.mean()
    var0 = float(np.var(x))

    def nll(p: np.ndarray) -> float:
        omega, alpha, beta = p
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.9999:
            return 1e10
        h = np.empty(x.size)
        h[0] = var0
        for t in range(1, x.size):
            h[t] = omega + alpha * x[t - 1] ** 2 + beta * h[t - 1]
        return 0.5 * float(np.sum(np.log(2 * np.pi * h) + x * x / h))

    best = None
    for a0, b0 in ((0.05, 0.9), (0.1, 0.8), (0.2, 0.6)):
        res = optimize.minimize(nll, np.array([var0 * (1 - a0 - b0), a0, b0]), method="Nelder-Mead",
                                options={"maxiter": 2000, "xatol": 1e-10, "fatol": 1e-8})
        if res.success and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        return None
    omega, alpha, beta = (float(v) for v in best.x)
    h = var0
    for t in range(1, x.size):
        h = omega + alpha * x[t - 1] ** 2 + beta * h
    persistence = alpha + beta
    long_run = omega / (1 - persistence) if persistence < 1 else None
    # Multi-step forecast of the variance, then the average over the horizon.
    h_next = omega + alpha * x[-1] ** 2 + beta * h
    path = []
    hk = h_next
    for _ in range(horizon):
        path.append(hk)
        hk = omega + persistence * hk
    return {
        "omega": omega, "alpha": alpha, "beta": beta, "persistence": persistence,
        "half_life_days": math.log(0.5) / math.log(persistence) if 0 < persistence < 1 else None,
        "current_volatility_pct": math.sqrt(h_next * TRADING_DAYS) * 100,
        "forecast_volatility_pct": math.sqrt(float(np.mean(path)) * TRADING_DAYS) * 100,
        "long_run_volatility_pct": math.sqrt(long_run * TRADING_DAYS) * 100 if long_run else None,
        "forecast_horizon_days": horizon,
    }


def drawdown(close: np.ndarray, dates: list[date]) -> dict[str, Any]:
    c = np.asarray(close, dtype=float)
    peak = np.maximum.accumulate(c)
    dd = c / peak - 1
    trough = int(np.argmin(dd))
    peak_i = int(np.argmax(c[:trough + 1])) if trough > 0 else 0
    recovered = next((i for i in range(trough, c.size) if c[i] >= c[peak_i]), None)
    cur_peak = int(np.argmax(c))
    return {
        "series": dd * 100,
        "max_drawdown_pct": float(dd.min() * 100),
        "max_drawdown_peak_date": dates[peak_i],
        "max_drawdown_trough_date": dates[trough],
        "max_drawdown_recovered_date": dates[recovered] if recovered is not None else None,
        "current_drawdown_pct": float(dd[-1] * 100),
        "days_since_peak": int(c.size - 1 - cur_peak),
    }


def value_at_risk(r: np.ndarray, confidence: float = 0.95, horizon: int = 1) -> dict[str, Any]:
    """Loss thresholds (positive % = loss) for one position over `horizon`
    sessions: historical, Gaussian and Cornish-Fisher (skew/kurtosis
    corrected) VaR, plus historical CVaR (expected shortfall)."""
    if r.size < 60:
        return {}
    alpha = 1 - confidence
    scale = math.sqrt(horizon)
    q_hist = float(np.quantile(r, alpha))
    cvar = float(r[r <= q_hist].mean())
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    z = stats.norm.ppf(alpha)
    s, k = float(stats.skew(r)), float(stats.kurtosis(r))
    z_cf = z + (z * z - 1) * s / 6 + (z ** 3 - 3 * z) * k / 24 - (2 * z ** 3 - 5 * z) * s * s / 36

    def loss(q: float) -> float:
        return (1 - math.exp(q * scale)) * 100

    return {
        "confidence": confidence,
        "horizon_days": horizon,
        "historical_var_pct": loss(q_hist),
        "parametric_var_pct": loss(mu + z * sd),
        "cornish_fisher_var_pct": loss(mu + z_cf * sd),
        "historical_cvar_pct": loss(cvar),
    }


def beta_vs_index(stock_dates: list[date], stock_close: np.ndarray, index_dates: list[date], index_close: np.ndarray,
                  window: int = 240) -> dict[str, Any] | None:
    """Beta, correlation, R^2 and annualised Jensen's alpha of the stock's
    daily log returns against the index over the last `window` common sessions."""
    idx = {d: v for d, v in zip(index_dates, index_close)}
    pairs = [(s, idx[d]) for d, s in zip(stock_dates, stock_close) if d in idx]
    if len(pairs) < 60:
        return None
    pairs = pairs[-(window + 1):]
    s = np.log(np.array([p[0] for p in pairs]))
    m = np.log(np.array([p[1] for p in pairs]))
    rs, rm = np.diff(s), np.diff(m)
    ok = np.isfinite(rs) & np.isfinite(rm)
    rs, rm = rs[ok], rm[ok]
    if rs.size < 50 or rm.var() == 0:
        return None
    beta = float(np.cov(rs, rm, ddof=1)[0, 1] / rm.var(ddof=1))
    corr = float(np.corrcoef(rs, rm)[0, 1])
    alpha = float((rs.mean() - beta * rm.mean()) * TRADING_DAYS * 100)
    return {"beta": beta, "correlation": corr, "r_squared": corr * corr, "alpha_annual_pct": alpha,
            "observations": int(rs.size), "index_volatility_pct": float(rm.std(ddof=1) * math.sqrt(TRADING_DAYS) * 100)}


def detect_jumps(r: np.ndarray, dates: list[date], window: int = 20, threshold: float = 4.0) -> dict[str, Any]:
    """Lee-Mykland style jump test: each return is standardised by the
    bipower-variation volatility of the previous `window` returns
    (robust to earlier jumps); |L| > threshold flags a jump. Also the share
    of total variation that is jump variation, (RV - BV) / RV, over the last
    year. `dates` align with r (the date each return ends on)."""
    if r.size < window + 10:
        return {}
    jumps = []
    for i in range(window, r.size):
        w = r[i - window:i]
        bv = (math.pi / 2) * np.mean(np.abs(w[1:]) * np.abs(w[:-1]))
        if bv <= 0:
            continue
        stat = r[i] / math.sqrt(bv)
        if abs(stat) > threshold:
            jumps.append({"date": dates[i], "return_pct": (math.exp(r[i]) - 1) * 100, "statistic": float(stat),
                          "direction": "up" if r[i] > 0 else "down"})
    year = r[-TRADING_DAYS:]
    rv = float(np.sum(year ** 2))
    bv_total = float((math.pi / 2) * np.sum(np.abs(year[1:]) * np.abs(year[:-1])))
    recent = [j for j in jumps if j["date"] >= dates[max(0, r.size - TRADING_DAYS)]]
    return {
        "threshold": threshold,
        "jumps_last_year": len(recent),
        "down_jumps_last_year": sum(1 for j in recent if j["direction"] == "down"),
        "jump_variation_share_pct": max(0.0, (rv - bv_total) / rv * 100) if rv else None,
        "recent_jumps": recent[-8:],
        "last_jump": jumps[-1] if jumps else None,
    }


def hurst_exponent(r: np.ndarray) -> float | None:
    """Rescaled-range (R/S) Hurst exponent of the return series: ~0.5
    random walk, >0.5 trending/persistent, <0.5 mean-reverting."""
    if r.size < 120:
        return None
    sizes = np.unique(np.floor(np.logspace(np.log10(8), np.log10(r.size // 2), 12)).astype(int))
    rs_vals, ns = [], []
    for n in sizes:
        chunks = r[: (r.size // n) * n].reshape(-1, n)
        dev = np.cumsum(chunks - chunks.mean(axis=1, keepdims=True), axis=1)
        rng = dev.max(axis=1) - dev.min(axis=1)
        sd = chunks.std(axis=1, ddof=1)
        ok = sd > 0
        if ok.any():
            rs_vals.append(float(np.mean(rng[ok] / sd[ok])))
            ns.append(n)
    if len(ns) < 4:
        return None
    return float(np.polyfit(np.log(ns), np.log(rs_vals), 1)[0])


def variance_ratio(r: np.ndarray, q: int) -> dict[str, float] | None:
    """Lo-MacKinlay variance ratio VR(q) with the homoskedastic z-test:
    VR>1 momentum, VR<1 mean reversion."""
    if r.size < q * 10:
        return None
    mu = r.mean()
    var1 = np.sum((r - mu) ** 2) / (r.size - 1)
    rq = np.convolve(r, np.ones(q), "valid")
    m = q * (r.size - q + 1) * (1 - q / r.size)
    varq = np.sum((rq - q * mu) ** 2) / m
    vr = varq / var1 if var1 else float("nan")
    z = (vr - 1) / math.sqrt(2 * (2 * q - 1) * (q - 1) / (3 * q * r.size))
    return {"q": q, "ratio": float(vr), "z": float(z), "p_value": float(2 * (1 - stats.norm.cdf(abs(z))))}


def monte_carlo(last_price: float, r: np.ndarray, days: int = 20, paths: int = 2000, method: str = "bootstrap",
                seed: int = 7) -> dict[str, Any] | None:
    """Simulated price distribution `days` sessions ahead from the last
    year's daily log returns: bootstrap (resampling actual returns, keeps
    fat tails) or GBM (normal with the same mean/std). Returns percentile
    paths and the probability of ending above the current price."""
    if r.size < 60 or last_price <= 0:
        return None
    rng = np.random.default_rng(seed)
    sample = r[-TRADING_DAYS:]
    if method == "gbm":
        steps = rng.normal(sample.mean(), sample.std(ddof=1), size=(paths, days))
    else:
        steps = rng.choice(sample, size=(paths, days), replace=True)
    prices = last_price * np.exp(np.cumsum(steps, axis=1))
    pct = np.percentile(prices, [5, 25, 50, 75, 95], axis=0)
    final = prices[:, -1]
    return {
        "method": method, "days": days, "paths": paths,
        "percentiles": {f"p{p}": pct[i] for i, p in enumerate((5, 25, 50, 75, 95))},
        "probability_up_pct": float((final > last_price).mean() * 100),
        "expected_price": float(final.mean()),
        "range_90": [float(pct[0][-1]), float(pct[4][-1])],
    }


def volatility_regime(r: np.ndarray, window: int = 20, history: int = 3 * TRADING_DAYS) -> dict[str, Any] | None:
    vol = rolling_volatility(r, window)
    vol = vol[~np.isnan(vol)]
    if vol.size < 120:
        return None
    hist = vol[-history:]
    current = float(vol[-1])
    pctile = float(stats.percentileofscore(hist, current))
    label = "extreme" if pctile >= 95 else "high" if pctile >= 75 else "low" if pctile <= 25 else "normal"
    return {"current_volatility_pct": current * 100, "percentile": pctile, "regime": label,
            "median_volatility_pct": float(np.median(hist) * 100)}


def return_histogram(r: np.ndarray, bins: int = 40) -> dict[str, Any]:
    pct = (np.exp(r) - 1) * 100
    counts, edges = np.histogram(pct, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    mu, sd = pct.mean(), pct.std(ddof=1)
    width = edges[1] - edges[0]
    normal = stats.norm.pdf(centers, mu, sd) * pct.size * width
    return {"centers": centers, "counts": counts, "normal": normal}
