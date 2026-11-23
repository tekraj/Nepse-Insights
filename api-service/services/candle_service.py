"""OHLCV candles for the candlestick page, any index or stock, at minute to
monthly timeframes.

Sources:
  * 1m..1h   -- market_intraday_tick (indices ~1 tick/min, stocks every
               print, both from 2018-03-29), bucketed here. Sessions it
               lacks (today until the 15:40 end-of-day job; stocks the
               per-stock backfill hasn't reached) come from the live
               1-minute scrapes since 2026-09-15: market_index_snapshot
               (index values, no volume) and market_price_snapshot (last
               traded price + cumulative volume per stock).
  * 1d/1w/1M -- market_index_daily / market_stock_daily, plus a provisional
               bar for today from the live scrapes while the session runs.

Bar timestamps are epoch milliseconds of the bucket start in NPT (the
chart formats them in Asia/Kathmandu). Index "volume" is NPR turnover.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

NPT = timezone(timedelta(hours=5, minutes=45))
INTRADAY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
TIMEFRAMES = (*INTRADAY_MINUTES, "1d", "1w", "1M")
# A session has ~240 one-minute ticks (11:00-15:00).
_TICKS_PER_SESSION = 240
# Since 2024 merolagani adds an index tick a few seconds after 15:00 that
# carries the whole day's turnover as its volume and the pre-close value as
# its price (the official close is the 15:00:00 tick): dropped.
_CLOSE_SUMMARY_FROM = dtime(15, 0)
# Start of the 1-minute live scrapes (market_index_snapshot / market_price_snapshot).
_LIVE_SINCE = datetime(2026, 9, 15)


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=NPT).timestamp() * 1000)


def _from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, NPT).replace(tzinfo=None)


def _now() -> datetime:
    return datetime.now(NPT).replace(tzinfo=None)


def _week_key(day: date) -> date:
    # Keyed by the Saturday before: Saturday has never been a session, so
    # the Sun-Thu weeks (until 2026-04-05), the Mon-Fri weeks since, and the
    # extra Fridays of 2022 each fall inside one key.
    return day - timedelta(days=(day.weekday() + 2) % 7)


def _bar(ts: datetime, o: float, h: float, l: float, c: float, v: float | None) -> dict[str, Any]:
    return {
        "timestamp": _ms(ts),
        "open": o,
        "high": max(h, o, c),
        "low": min(l, o, c),
        "close": c,
        "volume": v or 0,
    }


class CandleService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def candles(self, kind: str, symbol: str, tf: str, before_ms: int | None, limit: int, basis: str) -> dict[str, Any]:
        symbol = symbol if kind == "index" else symbol.strip().upper()
        before = _from_ms(before_ms) if before_ms else None
        adjust = kind == "stock" and basis == "adjusted"
        factors = self._adjust_factors(symbol) if adjust else None

        if tf in INTRADAY_MINUTES:
            bars, more = self._intraday(kind, symbol, INTRADAY_MINUTES[tf], before, limit, factors)
        else:
            bars, more = self._daily(kind, symbol, tf, before, limit, factors)
        return {
            "kind": kind,
            "symbol": symbol,
            "tf": tf,
            "basis": "adjusted" if adjust and factors else "raw",
            "timezone": "Asia/Kathmandu",
            "bars": bars,
            "more": more,
        }

    # -- adjustment ----------------------------------------------------

    def _adjust_factors(self, symbol: str) -> dict[date, float] | None:
        """trade_date -> adj_close / close (bonus/right adjustment), with
        days the weekly refresh hasn't adjusted yet carrying the nearest
        known factor. None when merolagani has no adjusted history."""
        rows = self._db.execute(
            text("SELECT trade_date, close, adj_close FROM market_stock_daily WHERE symbol = :s ORDER BY trade_date"),
            {"s": symbol},
        ).all()
        raw = [(r.trade_date, r.adj_close / r.close if r.adj_close and r.close else None) for r in rows]
        if not any(f for _, f in raw):
            return None
        first = next(f for _, f in raw if f)
        out, last = {}, first
        for day, f in raw:
            last = f or last
            out[day] = last
        return out

    @staticmethod
    def _factor(factors: dict[date, float] | None, day: date) -> float:
        if not factors:
            return 1.0
        if day in factors:
            return factors[day]
        # Today (no daily bar yet) or a gap: the latest earlier factor.
        earlier = [d for d in factors if d <= day]
        return factors[max(earlier)] if earlier else factors[min(factors)]

    # -- intraday ------------------------------------------------------

    def _intraday(
        self, kind: str, symbol: str, minutes: int, before: datetime | None, limit: int, factors: dict[date, float] | None
    ) -> tuple[list[dict[str, Any]], bool]:
        end = before or _now() + timedelta(days=1)
        ticks, start = self._window_ticks(kind, symbol, minutes, end, limit)
        if not ticks:
            # Nothing in the latest sessions (a delisted stock): jump to
            # where its ticks end instead of returning an empty page.
            last = self._db.execute(
                text("SELECT max(tick_time) FROM market_intraday_tick WHERE symbol = :s AND tick_time < :end"),
                {"s": symbol, "end": end},
            ).scalar()
            if last is not None:
                ticks, start = self._window_ticks(kind, symbol, minutes, last + timedelta(seconds=1), limit)

        buckets: dict[datetime, list[float]] = {}
        for t, price, volume in ticks:
            f = self._factor(factors, t.date()) if factors else 1.0
            p = round(price * f, 2)
            minute = (t.hour * 60 + t.minute) // minutes * minutes
            if minutes >= 60:
                # Hourly bars cover the 11:00-15:00 session: the closing
                # ticks (15:00:xx) belong to the last hour and pre-open
                # ticks (10:4x) to the first, not to bars of their own.
                minute = min(max(minute, 11 * 60), (15 * 60 - 1) // minutes * minutes)
            key = datetime.combine(t.date(), dtime(minute // 60, minute % 60))
            b = buckets.get(key)
            if b is None:
                buckets[key] = [p, p, p, p, volume or 0]
            else:
                b[1] = max(b[1], p)
                b[2] = min(b[2], p)
                b[3] = p
                b[4] += volume or 0
        bars = [_bar(k, *v) for k, v in sorted(buckets.items())][-limit:]
        return bars, len(buckets) > limit or self._has_older(kind, symbol, start)

    def _window_ticks(
        self, kind: str, symbol: str, minutes: int, end: datetime, limit: int
    ) -> tuple[list[tuple[datetime, float, float | None]], datetime]:
        """Ticks of the sessions needed for `limit` bars ending before `end`
        (by the NEPSE calendar), and the window start."""
        sessions = max(2, math.ceil(limit * minutes / _TICKS_PER_SESSION) + 1)
        days = self._db.execute(
            text(
                """
                SELECT trade_date FROM market_index_daily
                WHERE index_name = 'NEPSE' AND trade_date <= :end ORDER BY trade_date DESC LIMIT :n
                """
            ),
            {"end": end.date(), "n": sessions},
        ).scalars().all()
        start = datetime.combine(min(days), dtime(0, 0)) if days else end - timedelta(days=7)
        ticks = [
            (r.tick_time, r.price, r.volume)
            for r in self._db.execute(
                text(
                    """
                    SELECT tick_time, price, volume FROM market_intraday_tick
                    WHERE symbol = :s AND tick_time >= :start AND tick_time < :end ORDER BY tick_time
                    """
                ),
                {"s": symbol, "start": start, "end": end},
            ).all()
        ]
        covered = {t.date() for t, _, _ in ticks}
        if end > _LIVE_SINCE:
            ticks += self._snapshot_ticks(kind, symbol, max(start, _LIVE_SINCE), end, covered)
            ticks.sort(key=lambda t: t[0])
        if kind == "index":
            ticks = self._drop_close_summary(ticks)
        return ticks, start

    def _has_older(self, kind: str, symbol: str, start: datetime) -> bool:
        if self._db.execute(
            text("SELECT 1 FROM market_intraday_tick WHERE symbol = :s AND tick_time < :start LIMIT 1"),
            {"s": symbol, "start": start},
        ).first():
            return True
        if kind == "stock" and start > _LIVE_SINCE:
            return bool(
                self._db.execute(
                    text(
                        """
                        SELECT 1 FROM market_price_snapshot
                        WHERE symbol = :s AND scraped_at < :start AND scraped_at >= :live AND last_traded_price IS NOT NULL LIMIT 1
                        """
                    ),
                    {"s": symbol, "start": start, "live": _LIVE_SINCE},
                ).first()
            )
        return False

    @staticmethod
    def _drop_close_summary(ticks: list[tuple[datetime, float, float | None]]) -> list[tuple[datetime, float, float | None]]:
        by_day: dict[date, float] = {}
        for t, _, v in ticks:
            by_day[t.date()] = by_day.get(t.date(), 0) + (v or 0)
        return [
            (t, p, v)
            for t, p, v in ticks
            if not (v and t.time() >= _CLOSE_SUMMARY_FROM and v > 0.5 * (by_day[t.date()] - v))
        ]

    def _snapshot_ticks(
        self, kind: str, symbol: str, start: datetime, end: datetime, covered: set[date]
    ) -> list[tuple[datetime, float, float | None]]:
        """Ticks from the 1-minute live scrapes for the days in [start, end)
        that market_intraday_tick doesn't cover."""
        if kind == "index":
            rows = self._db.execute(
                text(
                    """
                    SELECT scraped_at, index_value FROM market_index_snapshot
                    WHERE index_name = :s AND scraped_at >= :start AND scraped_at < :end AND index_value IS NOT NULL
                    ORDER BY scraped_at
                    """
                ),
                {"s": symbol, "start": start, "end": end},
            ).all()
            return [(r.scraped_at, r.index_value, None) for r in rows if r.scraped_at.date() not in covered]
        rows = self._db.execute(
            text(
                """
                SELECT scraped_at, last_traded_price, volume FROM market_price_snapshot
                WHERE symbol = :s AND scraped_at >= :start AND scraped_at < :end AND last_traded_price IS NOT NULL
                ORDER BY scraped_at
                """
            ),
            {"s": symbol, "start": start, "end": end},
        ).all()
        out: list[tuple[datetime, float, float | None]] = []
        day, prev_qty = None, 0
        for r in rows:
            if r.scraped_at.date() in covered:
                continue
            if r.scraped_at.date() != day:
                day, prev_qty = r.scraped_at.date(), 0
            qty = r.volume or 0
            out.append((r.scraped_at, r.last_traded_price, max(qty - prev_qty, 0)))
            prev_qty = max(qty, prev_qty)
        return out

    # -- daily and longer ----------------------------------------------

    def _daily(
        self, kind: str, symbol: str, tf: str, before: datetime | None, limit: int, factors: dict[date, float] | None
    ) -> tuple[list[dict[str, Any]], bool]:
        if kind == "index":
            sql = """
                SELECT trade_date, open, high, low, close, turnover AS volume FROM market_index_daily
                WHERE index_name = :s AND close IS NOT NULL ORDER BY trade_date
            """
        else:
            sql = """
                SELECT trade_date, open, high, low, close, volume FROM market_stock_daily
                WHERE symbol = :s AND close IS NOT NULL ORDER BY trade_date
            """
        days: list[list[Any]] = []
        for r in self._db.execute(text(sql), {"s": symbol}).all():
            f = self._factor(factors, r.trade_date) if factors else 1.0
            o, h, l, c = (round((x if x is not None else r.close) * f, 2) for x in (r.open, r.high, r.low, r.close))
            days.append([r.trade_date, o, h, l, c, r.volume or 0])

        if before is None:
            today = self._today_bar(kind, symbol, factors)
            if today and (not days or today[0] > days[-1][0]):
                days.append(today)

        if tf == "1d":
            groups = [(d[0], d) for d in days]
        else:
            groups = []
            index: dict[date | str, int] = {}
            for d in days:
                key = _week_key(d[0]) if tf == "1w" else d[0].isoformat()[:7]
                if key not in index:
                    index[key] = len(groups)
                    groups.append((d[0], list(d)))
                else:
                    g = groups[index[key]][1]
                    g[2] = max(g[2], d[2])
                    g[3] = min(g[3], d[3])
                    g[4] = d[4]
                    g[5] += d[5]

        bars = [_bar(datetime.combine(first, dtime(0, 0)), g[1], g[2], g[3], g[4], g[5]) for first, g in groups]
        if before is not None:
            cutoff = _ms(before)
            bars = [b for b in bars if b["timestamp"] < cutoff]
        more = len(bars) > limit
        return bars[-limit:], more

    def _today_bar(self, kind: str, symbol: str, factors: dict[date, float] | None) -> list[Any] | None:
        """A provisional bar for today's session from the live scrapes."""
        today = _now().date()
        if kind == "index":
            row = self._db.execute(
                text(
                    """
                    SELECT (array_agg(index_value ORDER BY scraped_at))[1] AS o, max(index_value) AS h,
                           min(index_value) AS l, (array_agg(index_value ORDER BY scraped_at DESC))[1] AS c
                    FROM market_index_snapshot WHERE index_name = :s AND scraped_at >= :today AND index_value IS NOT NULL
                    """
                ),
                {"s": symbol, "today": today},
            ).first()
            if row is None or row.c is None:
                return None
            return [today, row.o, row.h, row.l, row.c, 0]
        row = self._db.execute(
            text(
                """
                SELECT open, high, low, last_traded_price, volume FROM market_price_snapshot
                WHERE symbol = :s AND trade_date = :today AND last_traded_price IS NOT NULL ORDER BY scraped_at DESC LIMIT 1
                """
            ),
            {"s": symbol, "today": today.isoformat()},
        ).first()
        if row is None:
            return None
        f = self._factor(factors, today) if factors else 1.0
        o, h, l, c = (
            round((x or row.last_traded_price) * f, 2) for x in (row.open, row.high, row.low, row.last_traded_price)
        )
        return [today, o, h, l, c, row.volume or 0]
