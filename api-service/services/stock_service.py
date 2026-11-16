"""Individual equities for the Technicals page: a searchable catalogue of
every stock in nepse_stock_daily (active and delisted) and its daily
series for the indicator charts.

Indicators run on the bonus/right-adjusted closes by default: raw prices
drop by the bonus ratio on every ex-date, which no moving average or RSI
should read as a crash. Raw prices stay available (basis="raw").
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.nepse_service import indicator_points

_CATALOGUE_CACHE_SECONDS = 600
_catalogue_cache: tuple[float, list[dict[str, Any]]] | None = None

_STATUS_LABELS = {"A": "Active", "S": "Suspended", "D": "Delisted"}


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


class StockService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def catalogue(self) -> list[dict[str, Any]]:
        """Every symbol with daily bars: name, sector, NEPSE status, history
        span, last close and change vs the previous session. Cached 10 min
        (the daily table only changes after the close)."""
        global _catalogue_cache
        now = time.monotonic()
        if _catalogue_cache is not None and now - _catalogue_cache[0] < _CATALOGUE_CACHE_SECONDS:
            return _catalogue_cache[1]

        rows = self._db.execute(
            text(
                """
                SELECT d.symbol, d.sessions, d.first_date, d.last_date, l.closes, l.turnover,
                       sec.company_name, sec.sector_name, sec.status, sec.instrument_type
                FROM (
                    SELECT symbol, count(*) AS sessions, min(trade_date) AS first_date, max(trade_date) AS last_date
                    FROM nepse_stock_daily GROUP BY symbol
                ) d
                CROSS JOIN LATERAL (
                    SELECT array_agg(close ORDER BY trade_date DESC) AS closes,
                           (array_agg(turnover ORDER BY trade_date DESC))[1] AS turnover
                    FROM (
                        SELECT trade_date, close, turnover FROM nepse_stock_daily x
                        WHERE x.symbol = d.symbol ORDER BY trade_date DESC LIMIT 2
                    ) y
                ) l
                LEFT JOIN LATERAL (
                    SELECT company_name, sector_name, status, instrument_type FROM nepse_security s
                    WHERE s.symbol = d.symbol
                    ORDER BY (s.status = 'A') DESC LIMIT 1
                ) sec ON true
                """
            )
        ).all()
        latest_session = max((r.last_date for r in rows), default=None)
        items = []
        for r in rows:
            close = r.closes[0] if r.closes else None
            prev = r.closes[1] if r.closes and len(r.closes) > 1 else None
            items.append(
                {
                    "symbol": r.symbol,
                    "name": r.company_name,
                    "sector": r.sector_name,
                    # Mostly "Equity"; a few debentures/mutual funds have daily bars too.
                    "type": r.instrument_type,
                    "status": _STATUS_LABELS.get(r.status, r.status) if r.status else None,
                    # Traded in the latest session: the default list and the
                    # search ranking put these first.
                    "trading": r.last_date == latest_session,
                    "sessions": r.sessions,
                    "first_date": r.first_date.isoformat(),
                    "last_date": r.last_date.isoformat(),
                    "close": close,
                    "change_pct": _round((close - prev) / prev * 100) if close and prev else None,
                    "turnover": r.turnover,
                }
            )
        _catalogue_cache = (now, items)
        return items

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Symbol or company-name matches, best first: exact symbol, symbol
        prefix, name word prefix, then anywhere in symbol/name/sector;
        stocks still trading before delisted ones. Without a query, the
        latest session's most traded stocks."""
        items = self.catalogue()
        q = query.strip().upper()
        if not q:
            ranked = sorted((i for i in items if i["trading"]), key=lambda i: -(i["turnover"] or 0))
            return ranked[:limit]

        def rank(item: dict[str, Any]) -> int | None:
            symbol = item["symbol"].upper()
            name = (item["name"] or "").upper()
            if symbol == q:
                return 0
            if symbol.startswith(q):
                return 1
            if any(word.startswith(q) for word in name.split()):
                return 2
            if q in symbol or q in name or q in (item["sector"] or "").upper():
                return 3
            return None

        scored = [(r, item) for item in items if (r := rank(item)) is not None]
        scored.sort(key=lambda p: (p[0], not p[1]["trading"], -(p[1]["turnover"] or 0), p[1]["symbol"]))
        return [item for _, item in scored[:limit]]

    def get_indicators(self, symbol: str, days: int, basis: str) -> dict[str, Any] | None:
        """Daily series + indicators for one stock, same shape as
        NepseIndexService.get_indicators plus volume and the stock's
        details. basis="adjusted": bonus/right-adjusted closes, each day
        scaled by its adj_close/close factor (days the weekly refresh
        hasn't adjusted yet reuse the nearest known factor); a stock with
        no adjusted history at all falls back to raw prices."""
        symbol = symbol.strip().upper()
        info = next((i for i in self.catalogue() if i["symbol"] == symbol), None)
        if info is None:
            return None
        rows = self._db.execute(
            text(
                """
                SELECT trade_date, close, adj_close, volume, turnover
                FROM nepse_stock_daily WHERE symbol = :symbol AND close IS NOT NULL ORDER BY trade_date
                """
            ),
            {"symbol": symbol},
        ).all()
        dates = [r.trade_date.isoformat() for r in rows]
        raw = [r.close for r in rows]

        factors: list[float | None] = [(r.adj_close / r.close) if r.adj_close and r.close else None for r in rows]
        adjusted_available = any(f is not None for f in factors)
        if basis == "adjusted" and adjusted_available:
            last = None
            for i, f in enumerate(factors):  # forward fill
                last = f if f is not None else last
                factors[i] = last
            first = next(f for f in factors if f is not None)
            factors = [f if f is not None else first for f in factors]  # back fill the head
            values = [_round(c * f) for c, f in zip(raw, factors)]
            used_basis = "adjusted"
        else:
            values = raw
            used_basis = "raw"

        payload = indicator_points(dates, values, days, extra={"raw_close": raw, "volume": [r.volume for r in rows], "turnover": [r.turnover for r in rows]})

        year_ago = (date.fromisoformat(dates[-1]) - timedelta(days=365)).isoformat() if dates else ""
        last_year = [v for d, v in zip(dates, values) if d >= year_ago and v is not None]
        return {
            "kind": "stock",
            "symbol": symbol,
            "index_name": symbol,
            **{k: info[k] for k in ("name", "sector", "type", "status", "trading", "first_date", "last_date", "close", "change_pct")},
            "basis": used_basis,
            "adjusted_available": adjusted_available,
            "high_52w": max(last_year) if last_year else None,
            "low_52w": min(last_year) if last_year else None,
            "days_requested": days,
            **payload,
        }
