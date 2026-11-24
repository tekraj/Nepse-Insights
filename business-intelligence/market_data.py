"""Read access to the market/news tables for the BI agents.

Everything here is synchronous SQLAlchemy (call it through
asyncio.to_thread from async code). Prices come from:

  market_stock_daily     daily OHLCV; adjusted prices use each day's
                         adj_close/close factor, forward-filled over days the
                         weekly refresh hasn't adjusted yet (same rule as the
                         dashboard's Technicals page).
  market_price_snapshot  the live session (1-minute scrapes since 2026-09-15):
                         a provisional bar for today until the end-of-day job
                         writes the official one.
  market_index_daily     index closes (NEPSE for beta / relative strength).

Fundamentals come from market_fundamental_daily / market_corporate_action,
which nepse-service's CompanyFundamentalsWorkflow fills daily. This service
never scrapes: it only reads the database and computes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import text

from nepse_common.config import load_app_config
from nepse_common.db.session import session_scope

from common import now_npt, today_npt

# A session counts as live when the newest price scrape is this fresh and
# carries today's businessDate (nepse-service scrapes every minute while
# NEPSE reports the market open).
LIVE_FRESHNESS = timedelta(minutes=3)


def _session():
    return session_scope(load_app_config().database)


# --------------------------------------------------------------------------
# Securities


def security_info(symbol: str) -> dict[str, Any] | None:
    with _session() as s:
        row = s.execute(
            text(
                """
                SELECT security_id, symbol, security_name, company_name, sector_name, instrument_type, listing_status
                FROM market_security WHERE symbol = :symbol
                ORDER BY (listing_status = 'A') DESC, updated_at DESC NULLS LAST LIMIT 1
                """
            ),
            {"symbol": symbol},
        ).mappings().first()
        return dict(row) if row else None


def securities_info(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT ON (symbol) symbol, company_name, sector_name, instrument_type, listing_status
                FROM market_security WHERE symbol = ANY(:symbols)
                ORDER BY symbol, (listing_status = 'A') DESC, updated_at DESC NULLS LAST
                """
            ),
            {"symbols": symbols},
        ).mappings().all()
        return {r["symbol"]: dict(r) for r in rows}


def has_daily_history(symbol: str) -> bool:
    with _session() as s:
        return bool(s.execute(text("SELECT 1 FROM market_stock_daily WHERE symbol = :s LIMIT 1"), {"s": symbol}).first())


def sector_peers(sector: str, exclude: str | None = None) -> list[str]:
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT symbol FROM market_security
                WHERE sector_name = :sector AND listing_status = 'A' AND instrument_type = 'Equity'
                """
            ),
            {"sector": sector},
        ).scalars().all()
    return sorted(r for r in rows if r != exclude)


# --------------------------------------------------------------------------
# Session state and live quotes


def session_state() -> dict[str, Any]:
    """Whether a NEPSE session is live right now, from the freshness of the
    1-minute price scrapes, plus the latest completed trading day."""
    with _session() as s:
        latest = s.execute(
            text(
                """
                SELECT scraped_at, trade_date FROM market_price_snapshot
                WHERE scraped_at > now() - interval '1 day' ORDER BY scraped_at DESC LIMIT 1
                """
            )
        ).first()
        last_day = s.execute(text("SELECT max(trade_date) FROM market_index_daily WHERE index_name = 'NEPSE'")).scalar()
    now = now_npt()
    live = bool(latest and latest.trade_date == today_npt().isoformat() and now - latest.scraped_at <= LIVE_FRESHNESS)
    return {
        "live": live,
        "latest_scrape_at": latest.scraped_at if latest else None,
        "latest_scrape_trade_date": latest.trade_date if latest else None,
        "last_trading_day": last_day,
    }


def live_quote(symbol: str) -> dict[str, Any] | None:
    """The newest 1-minute scrape of `symbol` from today's session, or None
    when it hasn't traded today."""
    with _session() as s:
        row = s.execute(
            text(
                """
                SELECT scraped_at, trade_date, last_traded_price, previous_close, percent_change, open, high, low,
                       volume, turnover, trade_count, average_traded_price, last_traded_at
                FROM market_price_snapshot
                WHERE symbol = :symbol AND scraped_at > now() - interval '20 hours' AND trade_date = :today
                ORDER BY scraped_at DESC LIMIT 1
                """
            ),
            {"symbol": symbol, "today": today_npt().isoformat()},
        ).mappings().first()
    return dict(row) if row else None


def live_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT ON (symbol) symbol, scraped_at, last_traded_price, previous_close, percent_change,
                       volume, turnover, trade_count
                FROM market_price_snapshot
                WHERE symbol = ANY(:symbols) AND scraped_at > now() - interval '20 hours' AND trade_date = :today
                ORDER BY symbol, scraped_at DESC
                """
            ),
            {"symbols": symbols, "today": today_npt().isoformat()},
        ).mappings().all()
    return {r["symbol"]: dict(r) for r in rows}


def intraday_path(symbol: str, trade_day: date | None = None) -> list[dict[str, Any]]:
    """Minute-by-minute last price and cumulative volume for one session
    (default today) from the live scrapes."""
    day = (trade_day or today_npt()).isoformat()
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT date_trunc('minute', scraped_at) AS t, max(last_traded_price) AS price, max(volume) AS volume
                FROM market_price_snapshot
                WHERE symbol = :symbol AND trade_date = :day AND scraped_at >= CAST(:day AS date)
                      AND scraped_at < CAST(:day AS date) + 1 AND last_traded_price IS NOT NULL
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"symbol": symbol, "day": day},
        ).mappings().all()
    return [{"time": r["t"], "price": r["price"], "volume": r["volume"]} for r in rows]


# --------------------------------------------------------------------------
# Daily bars


@dataclass
class Bars:
    """Daily OHLCV, oldest first. Prices are on `basis` (adjusted or raw);
    raw_close is always the as-traded close. `provisional_today` marks a
    last bar built from the live scrapes (no official close yet)."""

    symbol: str
    basis: str
    dates: list[date]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    turnover: np.ndarray
    raw_close: np.ndarray
    factor: np.ndarray
    provisional_today: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.dates)

    def since(self, start: date) -> int:
        """Index of the first bar on/after `start`."""
        for i, d in enumerate(self.dates):
            if d >= start:
                return i
        return len(self.dates)


def _ffill_factors(factors: list[float | None]) -> np.ndarray:
    last = None
    out: list[float | None] = []
    for f in factors:
        last = f if f is not None else last
        out.append(last)
    first = next((f for f in out if f is not None), 1.0)
    return np.array([f if f is not None else first for f in out], dtype=float)


def daily_bars(symbol: str, basis: str = "adjusted", start: date | None = None, include_live: bool = True) -> Bars:
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT trade_date, open, high, low, close, adj_close, volume, turnover
                FROM market_stock_daily
                WHERE symbol = :symbol AND close IS NOT NULL AND (CAST(:start AS date) IS NULL OR trade_date >= :start)
                ORDER BY trade_date
                """
            ),
            {"symbol": symbol, "start": start},
        ).all()
    dates = [r.trade_date for r in rows]
    raw = {k: np.array([getattr(r, k) if getattr(r, k) is not None else np.nan for r in rows], dtype=float) for k in ("open", "high", "low", "close", "volume", "turnover")}
    factors_raw = [(r.adj_close / r.close) if r.adj_close and r.close else None for r in rows]
    use_adjusted = basis == "adjusted" and any(f is not None for f in factors_raw)
    factor = _ffill_factors(factors_raw) if use_adjusted else np.ones(len(rows))

    provisional = False
    if include_live:
        quote = live_quote(symbol)
        today = today_npt()
        if quote and quote.get("last_traded_price") and (not dates or dates[-1] < today):
            ltp = float(quote["last_traded_price"])
            dates.append(today)
            for k, v in (("open", quote.get("open") or ltp), ("high", quote.get("high") or ltp), ("low", quote.get("low") or ltp),
                         ("close", ltp), ("volume", quote.get("volume") or 0), ("turnover", quote.get("turnover") or 0)):
                raw[k] = np.append(raw[k], float(v))
            factor = np.append(factor, factor[-1] if factor.size else 1.0)
            provisional = True

    # For missing open/high/low (some merolagani rows carry close only) use the close.
    for k in ("open", "high", "low"):
        raw[k] = np.where(np.isnan(raw[k]), raw["close"], raw[k])

    return Bars(
        symbol=symbol,
        basis="adjusted" if use_adjusted else "raw",
        dates=dates,
        open=raw["open"] * factor,
        high=raw["high"] * factor,
        low=raw["low"] * factor,
        close=raw["close"] * factor,
        # More shares after a bonus: scale old volumes the other way so
        # volume stays comparable across the ex-date.
        volume=np.where(factor > 0, raw["volume"] / factor, raw["volume"]),
        turnover=raw["turnover"],
        raw_close=raw["close"],
        factor=factor,
        provisional_today=provisional,
    )


def index_closes(index_name: str = "NEPSE", start: date | None = None) -> tuple[list[date], np.ndarray]:
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT trade_date, close FROM market_index_daily
                WHERE index_name = :name AND close IS NOT NULL AND (CAST(:start AS date) IS NULL OR trade_date >= :start)
                ORDER BY trade_date
                """
            ),
            {"name": index_name, "start": start},
        ).all()
    return [r.trade_date for r in rows], np.array([r.close for r in rows], dtype=float)


def adjusted_closes_many(symbols: list[str], start: date) -> dict[str, tuple[list[date], np.ndarray]]:
    """Adjusted daily closes for several symbols in one query (sector comparisons)."""
    if not symbols:
        return {}
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT symbol, trade_date, close, adj_close FROM market_stock_daily
                WHERE symbol = ANY(:symbols) AND trade_date >= :start AND close IS NOT NULL
                ORDER BY symbol, trade_date
                """
            ),
            {"symbols": symbols, "start": start},
        ).all()
    grouped: dict[str, list[Any]] = {}
    for r in rows:
        grouped.setdefault(r.symbol, []).append(r)
    out = {}
    for sym, rs in grouped.items():
        factor = _ffill_factors([(r.adj_close / r.close) if r.adj_close and r.close else None for r in rs])
        out[sym] = ([r.trade_date for r in rs], np.array([r.close for r in rs], dtype=float) * factor)
    return out


def average_volume(symbol: str, sessions: int = 20) -> float | None:
    """Mean raw daily volume over the last `sessions` completed sessions."""
    with _session() as s:
        value = s.execute(
            text(
                """
                SELECT avg(volume) FROM (
                    SELECT volume FROM market_stock_daily WHERE symbol = :symbol AND volume IS NOT NULL AND trade_date < :today
                    ORDER BY trade_date DESC LIMIT :n
                ) t
                """
            ),
            {"symbol": symbol, "n": sessions, "today": today_npt()},
        ).scalar()
    return float(value) if value is not None else None


def latest_daily_bar_date(symbol: str) -> date | None:
    with _session() as s:
        return s.execute(text("SELECT max(trade_date) FROM market_stock_daily WHERE symbol = :s"), {"s": symbol}).scalar()


# --------------------------------------------------------------------------
# Fundamentals (filled by nepse-service's CompanyFundamentalsWorkflow)


def fundamentals(symbol: str, history_days: int = 400) -> dict[str, Any]:
    """Latest fundamentals row plus the P/E, P/BV and EPS history."""
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT * FROM market_fundamental_daily
                WHERE symbol = :symbol AND trade_date >= :since ORDER BY trade_date
                """
            ),
            {"symbol": symbol, "since": today_npt() - timedelta(days=history_days)},
        ).mappings().all()
        actions = s.execute(
            text(
                """
                SELECT action_type, fiscal_year, seq, value_pct FROM market_corporate_action
                WHERE symbol = :symbol ORDER BY action_type, fiscal_year DESC, seq
                """
            ),
            {"symbol": symbol},
        ).mappings().all()
    latest = dict(rows[-1]) if rows else None
    return {
        "latest": latest,
        "history": [{"date": r["trade_date"], "pe_ratio": r["pe_ratio"], "pbv": r["pbv"], "eps": r["eps"],
                     "market_price": r["market_price"]} for r in rows],
        "corporate_actions": [dict(a) for a in actions],
    }


def sector_fundamentals(sector: str, max_age_days: int = 10) -> list[dict[str, Any]]:
    """Each active equity's latest fundamentals in `sector`."""
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT ON (f.symbol) f.symbol, f.trade_date, f.market_price, f.eps, f.pe_ratio, f.book_value, f.pbv,
                       f.cash_dividend_pct, f.bonus_pct, f.market_cap, f.paidup_value
                FROM market_fundamental_daily f
                JOIN market_security ms ON ms.symbol = f.symbol AND ms.listing_status = 'A' AND ms.instrument_type = 'Equity'
                WHERE ms.sector_name = :sector AND f.trade_date >= :since
                ORDER BY f.symbol, f.trade_date DESC
                """
            ),
            {"sector": sector, "since": today_npt() - timedelta(days=max_age_days)},
        ).mappings().all()
    return [dict(r) for r in rows]


def latest_fundamentals_date(symbol: str) -> date | None:
    with _session() as s:
        return s.execute(text("SELECT max(trade_date) FROM market_fundamental_daily WHERE symbol = :s"), {"s": symbol}).scalar()


# --------------------------------------------------------------------------
# Floor sheet (broker activity)


def broker_flows(symbol: str, since: date) -> dict[str, Any]:
    """Per-broker bought/sold quantity and amount for `symbol` since `since`
    (market_trade; broker codes exist for every session since 2020)."""
    with _session() as s:
        rows = s.execute(
            text(
                """
                WITH t AS (
                    SELECT buyer_broker_code, seller_broker_code, quantity, amount
                    FROM market_trade WHERE symbol = :symbol AND trade_date >= :since
                ),
                b AS (SELECT buyer_broker_code AS code, sum(quantity) AS qty, sum(amount) AS amt FROM t
                      WHERE buyer_broker_code IS NOT NULL GROUP BY 1),
                s AS (SELECT seller_broker_code AS code, sum(quantity) AS qty, sum(amount) AS amt FROM t
                      WHERE seller_broker_code IS NOT NULL GROUP BY 1)
                SELECT coalesce(b.code, s.code) AS code, coalesce(b.qty, 0) AS bought, coalesce(s.qty, 0) AS sold,
                       coalesce(b.amt, 0) AS bought_amount, coalesce(s.amt, 0) AS sold_amount, mb.broker_name
                FROM b FULL OUTER JOIN s ON b.code = s.code
                LEFT JOIN market_broker mb ON mb.broker_code = coalesce(b.code, s.code)
                """
            ),
            {"symbol": symbol, "since": since.isoformat()},
        ).mappings().all()
        totals = s.execute(
            text(
                """
                SELECT count(*) AS trades, coalesce(sum(quantity), 0) AS quantity, coalesce(sum(amount), 0) AS amount,
                       count(DISTINCT trade_date) AS sessions, min(trade_date) AS first_day, max(trade_date) AS last_day
                FROM market_trade WHERE symbol = :symbol AND trade_date >= :since
                """
            ),
            {"symbol": symbol, "since": since.isoformat()},
        ).mappings().first()
    brokers = [
        {
            "broker_code": r["code"],
            "broker_name": r["broker_name"],
            "bought": float(r["bought"]),
            "sold": float(r["sold"]),
            "net": float(r["bought"]) - float(r["sold"]),
            "bought_amount": float(r["bought_amount"]),
            "sold_amount": float(r["sold_amount"]),
        }
        for r in rows
    ]
    return {"brokers": brokers, "totals": dict(totals) if totals else {}}


# --------------------------------------------------------------------------
# News

_COMPANY_SUFFIXES = re.compile(
    r"\b(limited|ltd\.?|company|co\.?|public|pvt\.?|private|inc\.?)\s*$", re.IGNORECASE
)

MARKET_NEWS_TERMS = [
    "NEPSE", "SEBON", "Nepal Rastra Bank", "NRB", "monetary policy", "interest rate", "share market", "stock market",
    "नेप्से", "राष्ट्र बैंक", "धितोपत्र", "सेयर बजार", "मौद्रिक नीति",
]


def company_core_name(company_name: str | None) -> str | None:
    """'Nabil Bank Limited' -> 'Nabil Bank' (suffixes stripped repeatedly)."""
    if not company_name:
        return None
    name = company_name.strip().rstrip(".,")
    while True:
        stripped = _COMPANY_SUFFIXES.sub("", name).strip().rstrip(".,")
        if stripped == name:
            break
        name = stripped
    return name if len(name) >= 4 else None


def _term_clauses(symbol: str | None, terms: list[str], params: dict[str, Any]) -> list[str]:
    clauses = []
    if symbol:
        # Case-sensitive, whole word: tickers like API or HDL are ordinary
        # words in lower case.
        params["sym_rx"] = rf"\m{re.escape(symbol)}\M"
        clauses.append("(title ~ :sym_rx OR body ~ :sym_rx)")
    for i, term in enumerate(t for t in terms if t and t.strip()):
        term = term.strip()
        if term.isascii():
            params[f"t{i}"] = rf"\m{re.escape(term)}\M"
            clauses.append(f"(title ~* :t{i} OR body ~* :t{i})")
        else:  # Devanagari: \m/\M word boundaries don't apply
            params[f"t{i}"] = f"%{term}%"
            clauses.append(f"(title ILIKE :t{i} OR body ILIKE :t{i})")
    return clauses


def news_mentioning(symbol: str | None, terms: list[str], days: int, limit: int, body_chars: int = 1500,
                    since_id: int | None = None) -> list[dict[str, Any]]:
    """Recent articles whose title/body mention the symbol or any term,
    newest first (by published time, scrape time when unknown)."""
    params: dict[str, Any] = {"since": now_npt() - timedelta(days=days), "limit": limit, "chars": body_chars}
    clauses = _term_clauses(symbol, terms, params)
    if not clauses:
        return []
    extra = ""
    if since_id is not None:
        params["since_id"] = since_id
        extra = "AND id > :since_id"
    with _session() as s:
        rows = s.execute(
            text(
                f"""
                SELECT id, source, portal_tier, url, title, left(body, :chars) AS body, category, published_at, scraped_at
                FROM news_article
                WHERE coalesce(published_at, scraped_at) >= :since {extra} AND ({' OR '.join(clauses)})
                ORDER BY coalesce(published_at, scraped_at) DESC, id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]


def market_news(days: int, limit: int) -> list[dict[str, Any]]:
    """Recent market-wide news from the finance portals (NEPSE, SEBON, NRB, policy)."""
    params: dict[str, Any] = {"since": now_npt() - timedelta(days=days), "limit": limit}
    clauses = _term_clauses(None, MARKET_NEWS_TERMS, params)
    with _session() as s:
        rows = s.execute(
            text(
                f"""
                SELECT id, source, portal_tier, url, title, left(body, 800) AS body, category, published_at, scraped_at
                FROM news_article
                WHERE portal_tier = 'finance' AND coalesce(published_at, scraped_at) >= :since AND ({' OR '.join(clauses)})
                ORDER BY coalesce(published_at, scraped_at) DESC, id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]


def news_search(query: str, days: int, limit: int) -> list[dict[str, Any]]:
    """Free-text news search for the Q&A tools: every word must appear."""
    words = [w for w in re.split(r"\s+", query.strip()) if len(w) >= 2][:6]
    if not words:
        return []
    params: dict[str, Any] = {"since": now_npt() - timedelta(days=days), "limit": limit}
    clauses = []
    for i, w in enumerate(words):
        params[f"w{i}"] = f"%{w}%"
        clauses.append(f"(title ILIKE :w{i} OR body ILIKE :w{i})")
    with _session() as s:
        rows = s.execute(
            text(
                f"""
                SELECT id, source, url, title, left(body, 1200) AS body, published_at, scraped_at
                FROM news_article
                WHERE coalesce(published_at, scraped_at) >= :since AND {' AND '.join(clauses)}
                ORDER BY coalesce(published_at, scraped_at) DESC, id DESC LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]


def latest_news_id() -> int:
    with _session() as s:
        return int(s.execute(text("SELECT coalesce(max(id), 0) FROM news_article")).scalar())
