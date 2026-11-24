"""Price levels and candlestick patterns: swing-based support/resistance,
Fibonacci retracements, classic pivot points."""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np


def swing_points(high: np.ndarray, low: np.ndarray, window: int = 5) -> tuple[list[int], list[int]]:
    """Indices of swing highs/lows: the extreme of a +-window neighbourhood."""
    highs, lows = [], []
    for i in range(window, len(high) - window):
        h = high[i - window:i + window + 1]
        l_ = low[i - window:i + window + 1]
        if high[i] == np.nanmax(h):
            highs.append(i)
        if low[i] == np.nanmin(l_):
            lows.append(i)
    return highs, lows


def support_resistance(high: np.ndarray, low: np.ndarray, close: np.ndarray, lookback: int = 120,
                       levels: int = 3, tolerance_pct: float = 1.5) -> dict[str, Any]:
    """Cluster swing highs/lows of the last `lookback` sessions into price
    zones (within tolerance_pct of each other); each zone's strength is its
    number of touches. Supports are zones below the last close, resistances
    above it, nearest first."""
    n = len(close)
    start = max(0, n - lookback)
    h, l_, c = high[start:], low[start:], close[start:]
    if len(c) < 15:
        return {"supports": [], "resistances": []}
    sh, sl = swing_points(h, l_, window=3 if len(c) < 60 else 5)
    points = [(float(h[i]), start + i) for i in sh] + [(float(l_[i]), start + i) for i in sl]
    points.sort()
    zones: list[dict[str, Any]] = []
    for price, idx in points:
        if zones and abs(price / zones[-1]["price"] - 1) * 100 <= tolerance_pct:
            z = zones[-1]
            z["prices"].append(price)
            z["price"] = float(np.mean(z["prices"]))
            z["touches"] += 1
            z["last_index"] = max(z["last_index"], idx)
        else:
            zones.append({"price": price, "prices": [price], "touches": 1, "last_index": idx})
    last = float(close[-1])
    supports = sorted((z for z in zones if z["price"] < last), key=lambda z: -z["price"])[:levels]
    resistances = sorted((z for z in zones if z["price"] > last), key=lambda z: z["price"])[:levels]

    def fmt(z: dict[str, Any]) -> dict[str, Any]:
        return {"price": z["price"], "touches": z["touches"], "distance_pct": (z["price"] / last - 1) * 100}

    return {"supports": [fmt(z) for z in supports], "resistances": [fmt(z) for z in resistances]}


FIB_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def fibonacci(high: np.ndarray, low: np.ndarray, dates: list[date], lookback: int = 120) -> dict[str, Any] | None:
    """Retracement levels of the swing between the highest high and lowest
    low of the last `lookback` sessions. In an up-swing (low before high)
    levels retrace down from the high; in a down-swing up from the low."""
    n = len(high)
    if n < 10:
        return None
    start = max(0, n - lookback)
    hi_i = start + int(np.nanargmax(high[start:]))
    lo_i = start + int(np.nanargmin(low[start:]))
    hi, lo = float(high[hi_i]), float(low[lo_i])
    if hi <= lo:
        return None
    up = lo_i < hi_i
    levels = [{"ratio": r, "price": hi - r * (hi - lo) if up else lo + r * (hi - lo)} for r in FIB_RATIOS]
    return {"direction": "up" if up else "down", "swing_high": hi, "swing_low": lo,
            "swing_high_date": dates[hi_i], "swing_low_date": dates[lo_i], "levels": levels}


def pivot_points(high: float, low: float, close: float) -> dict[str, float]:
    """Classic floor-trader pivots from one session's H/L/C (for the next session)."""
    p = (high + low + close) / 3
    return {"pivot": p, "r1": 2 * p - low, "s1": 2 * p - high, "r2": p + (high - low), "s2": p - (high - low),
            "r3": high + 2 * (p - low), "s3": low - 2 * (high - p)}


def candlestick_patterns(o: np.ndarray, h: np.ndarray, l_: np.ndarray, c: np.ndarray, dates: list[date],
                         recent: int = 10) -> list[dict[str, Any]]:
    """Classic single/double/triple-bar patterns among the last `recent`
    bars. Context (prior trend) uses the 5 bars before the pattern."""
    out: list[dict[str, Any]] = []
    n = len(c)
    for i in range(max(3, n - recent), n):
        body = c[i] - o[i]
        rng = h[i] - l_[i]
        if rng <= 0 or np.isnan(rng):
            continue
        upper = h[i] - max(o[i], c[i])
        lower = min(o[i], c[i]) - l_[i]
        prior = c[max(0, i - 5):i]
        downtrend = prior.size >= 3 and prior[-1] < prior[0]
        uptrend = prior.size >= 3 and prior[-1] > prior[0]
        found: list[tuple[str, str]] = []
        if abs(body) <= 0.1 * rng:
            found.append(("Doji", "neutral"))
        if lower >= 2 * abs(body) and upper <= 0.3 * abs(body) + 0.1 * rng and abs(body) > 0:
            found.append(("Hammer", "bullish") if downtrend else ("Hanging man", "bearish") if uptrend else ("Hammer", "neutral"))
        if upper >= 2 * abs(body) and lower <= 0.3 * abs(body) + 0.1 * rng and abs(body) > 0:
            found.append(("Shooting star", "bearish") if uptrend else ("Inverted hammer", "bullish") if downtrend else ("Shooting star", "neutral"))
        pb = c[i - 1] - o[i - 1]
        if pb < 0 < body and o[i] <= c[i - 1] and c[i] >= o[i - 1]:
            found.append(("Bullish engulfing", "bullish"))
        if pb > 0 > body and o[i] >= c[i - 1] and c[i] <= o[i - 1]:
            found.append(("Bearish engulfing", "bearish"))
        if i >= 2:
            b2 = c[i - 2] - o[i - 2]
            small_mid = abs(c[i - 1] - o[i - 1]) <= 0.3 * abs(b2) if b2 else False
            if b2 < 0 and small_mid and body > 0 and c[i] > (o[i - 2] + c[i - 2]) / 2:
                found.append(("Morning star", "bullish"))
            if b2 > 0 and small_mid and body < 0 and c[i] < (o[i - 2] + c[i - 2]) / 2:
                found.append(("Evening star", "bearish"))
            if all(c[j] > o[j] for j in (i - 2, i - 1, i)) and c[i] > c[i - 1] > c[i - 2]:
                found.append(("Three white soldiers", "bullish"))
            if all(c[j] < o[j] for j in (i - 2, i - 1, i)) and c[i] < c[i - 1] < c[i - 2]:
                found.append(("Three black crows", "bearish"))
        for name, direction in found:
            out.append({"date": dates[i], "pattern": name, "direction": direction, "bars_ago": n - 1 - i})
    return out
