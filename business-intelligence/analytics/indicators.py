"""Technical indicators over numpy arrays (oldest first).

Every function returns arrays aligned with its inputs, NaN until the
indicator's window has enough history. Definitions follow the usual
references: EMA seeded with the SMA of its first window, Wilder smoothing
(RMA) for RSI/ATR/ADX, MACD as EMA(fast) - EMA(slow).
"""
from __future__ import annotations

import numpy as np


def _nan(n: int) -> np.ndarray:
    return np.full(n, np.nan)


def sma(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    if n <= 0 or len(x) < n:
        return out
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    # Windows containing a NaN input stay NaN.
    bad = np.convolve(np.isnan(x).astype(int), np.ones(n, dtype=int), "valid") > 0
    out[n - 1:][bad] = np.nan
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    valid = np.flatnonzero(~np.isnan(x))
    if n <= 0 or valid.size < n:
        return out
    start = valid[0]
    if np.isnan(x[start:start + n]).any():
        return out
    alpha = 2.0 / (n + 1)
    out[start + n - 1] = x[start:start + n].mean()
    for i in range(start + n, len(x)):
        out[i] = out[i - 1] if np.isnan(x[i]) else alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def rma(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's smoothing (EMA with alpha = 1/n), seeded with the SMA."""
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    valid = np.flatnonzero(~np.isnan(x))
    if n <= 0 or valid.size < n:
        return out
    start = valid[0]
    out[start + n - 1] = np.nanmean(x[start:start + n])
    for i in range(start + n, len(x)):
        out[i] = out[i - 1] if np.isnan(x[i]) else (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = np.nanmax(x[i - n + 1:i + 1])
    return out


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = np.nanmin(x[i - n + 1:i + 1])
    return out


def rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if not np.isnan(w).any():
            out[i] = w.std(ddof=0)
    return out


def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(close, prepend=np.nan)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    gain[0] = loss[0] = np.nan
    avg_gain, avg_loss = rma(gain, n), rma(loss, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100 - 100 / (1 + rs)
    out = np.where((avg_loss == 0) & (avg_gain > 0), 100.0, out)
    out = np.where((avg_loss == 0) & (avg_gain == 0), 50.0, out)
    return out


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, np.ndarray]:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return {"macd": line, "signal": sig, "histogram": line - sig}


def bollinger(close: np.ndarray, n: int = 20, k: float = 2.0) -> dict[str, np.ndarray]:
    mid = sma(close, n)
    sd = rolling_std(close, n)
    upper, lower = mid + k * sd, mid - k * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        pct_b = (close - lower) / (upper - lower)
        bandwidth = (upper - lower) / mid
    return {"middle": mid, "upper": upper, "lower": lower, "percent_b": pct_b, "bandwidth": bandwidth}


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k: int = 14, d: int = 3, smooth: int = 3) -> dict[str, np.ndarray]:
    hh, ll = rolling_max(high, k), rolling_min(low, k)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_k = 100 * (close - ll) / (hh - ll)
    raw_k = np.where(hh == ll, 50.0, raw_k)
    k_line = sma(raw_k, smooth) if smooth > 1 else raw_k
    return {"k": k_line, "d": sma(k_line, d)}


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev = np.roll(close, 1)
    prev[0] = np.nan
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev), np.abs(low - prev)]), axis=0)
    tr[0] = high[0] - low[0]
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    return rma(true_range(high, low, close), n)


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> dict[str, np.ndarray]:
    up = np.diff(high, prepend=np.nan)
    down = -np.diff(low, prepend=np.nan)
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm[0] = minus_dm[0] = np.nan
    tr = true_range(high, low, close)
    tr[0] = np.nan
    atr_n = rma(tr, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100 * rma(plus_dm, n) / atr_n
        minus_di = 100 * rma(minus_dm, n) / atr_n
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    return {"adx": rma(dx, n), "plus_di": plus_di, "minus_di": minus_di}


def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(np.nan_to_num(volume) * direction)


def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 20) -> np.ndarray:
    tp = (high + low + close) / 3
    ma = sma(tp, n)
    out = _nan(len(tp))
    for i in range(n - 1, len(tp)):
        md = np.mean(np.abs(tp[i - n + 1:i + 1] - ma[i]))
        out[i] = (tp[i] - ma[i]) / (0.015 * md) if md else 0.0
    return out


def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    hh, ll = rolling_max(high, n), rolling_min(low, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = -100 * (hh - close) / (hh - ll)
    return np.where(hh == ll, -50.0, out)


def mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, n: int = 14) -> np.ndarray:
    tp = (high + low + close) / 3
    flow = tp * np.nan_to_num(volume)
    d = np.diff(tp, prepend=np.nan)
    pos = np.where(d > 0, flow, 0.0)
    neg = np.where(d < 0, flow, 0.0)
    out = _nan(len(tp))
    for i in range(n, len(tp)):
        p, q = pos[i - n + 1:i + 1].sum(), neg[i - n + 1:i + 1].sum()
        out[i] = 100.0 if q == 0 else 100 - 100 / (1 + p / q)
    return out


def rolling_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, n: int = 20) -> np.ndarray:
    tp = (high + low + close) / 3
    v = np.nan_to_num(volume)
    num, den = sma(tp * v, n), sma(v, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return num / den


def ichimoku(high: np.ndarray, low: np.ndarray, close: np.ndarray, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> dict[str, np.ndarray]:
    """Spans are shifted forward by `kijun` sessions (as plotted), so the
    cloud value at index i is the one projected for that session."""
    conv = (rolling_max(high, tenkan) + rolling_min(low, tenkan)) / 2
    base = (rolling_max(high, kijun) + rolling_min(low, kijun)) / 2
    span_a = (conv + base) / 2
    span_b = (rolling_max(high, senkou) + rolling_min(low, senkou)) / 2

    def shift(a: np.ndarray, k: int) -> np.ndarray:
        out = _nan(len(a))
        if k < len(a):
            out[k:] = a[:-k]
        return out

    return {"tenkan": conv, "kijun": base, "span_a": shift(span_a, kijun), "span_b": shift(span_b, kijun)}


def slope(x: np.ndarray, n: int) -> float | None:
    """Least-squares slope of the last n valid points, per step, relative to their mean."""
    y = np.asarray(x, dtype=float)[-n:]
    y = y[~np.isnan(y)]
    if y.size < max(3, n // 2):
        return None
    t = np.arange(y.size)
    m = np.polyfit(t, y, 1)[0]
    mean = np.abs(y).mean()
    return float(m / mean) if mean else None
