"""Small helpers shared across the business-intelligence service."""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

NPT = ZoneInfo("Asia/Kathmandu")


def now_npt() -> datetime:
    """Naive NPT wall-clock time -- the convention of every timestamp column."""
    return datetime.now(NPT).replace(tzinfo=None)


def today_npt() -> date:
    return now_npt().date()


def clean(value: Any, digits: int | None = 4) -> Any:
    """Make a value JSON-safe: numpy scalars/arrays -> Python, NaN/inf ->
    None, Decimal -> float, dates -> ISO strings, floats rounded."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): clean(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v, digits) for v in value]
    if isinstance(value, np.ndarray):
        return [clean(v, digits) for v in value.tolist()]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, digits) if digits is not None else f
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


def last_valid(values: Any) -> float | None:
    """Last non-NaN element of a 1-D array/list, or None."""
    arr = np.asarray(values, dtype=float)
    idx = np.flatnonzero(~np.isnan(arr))
    return float(arr[idx[-1]]) if idx.size else None


def pct(a: float | None, b: float | None) -> float | None:
    """Percent change from b to a."""
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


RECOMMENDATIONS = ("strong_sell", "sell", "hold", "buy", "strong_buy")


def recommendation_from_score(score: float) -> str:
    """Map a -100..100 outlook score onto the five recommendation buckets."""
    if score >= 45:
        return "strong_buy"
    if score >= 15:
        return "buy"
    if score > -15:
        return "hold"
    if score > -45:
        return "sell"
    return "strong_sell"
