"""Company fundamentals (merolagani company pages) -> market_fundamental_daily
+ market_corporate_action. Driven by CompanyFundamentalsWorkflow."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from temporalio import activity

from nepse_common.config import load_app_config
from nepse_common.db.session import session_scope
from nepse_common.db.upserts import replace_corporate_actions, upsert_fundamentals_daily

from scraper.merolagani_fundamentals import FundamentalsNotFound, fetch_company_fundamentals


def _today_npt() -> date:
    # Container TZ is Asia/Kathmandu (docker-compose), like every other job here.
    return datetime.now().date()


@activity.defn
async def fundamentals_due_activity(force: bool) -> dict[str, Any]:
    """Run when forced, when the table is empty or stale (first deploy, a
    missed week), or when today had a session (today's official bars are in
    market_stock_daily) and today's fundamentals aren't complete yet."""

    def check() -> dict[str, Any]:
        with session_scope(load_app_config().database) as s:
            latest_scrape = s.execute(text("SELECT max(scraped_at) FROM market_fundamental_daily")).scalar()
            session_today = s.execute(
                text("SELECT count(*) FROM market_stock_daily WHERE trade_date = :d"), {"d": _today_npt()}
            ).scalar()
        if force:
            return {"due": True, "reason": "forced"}
        if latest_scrape is None or latest_scrape < datetime.now() - timedelta(days=4):
            return {"due": True, "reason": "stale" if latest_scrape else "empty"}
        if session_today:
            return {"due": True, "reason": "session today"}
        return {"due": False, "reason": "no session today"}

    return await asyncio.to_thread(check)


@activity.defn
async def fundamentals_symbols_activity() -> list[str]:
    """Every listed (active) equity, plus scripts set up for business
    intelligence even if suspended."""

    def load() -> list[str]:
        with session_scope(load_app_config().database) as s:
            rows = s.execute(
                text(
                    """
                    SELECT DISTINCT symbol FROM market_security WHERE instrument_type = 'Equity' AND listing_status = 'A'
                    UNION SELECT symbol FROM bi_setting
                    ORDER BY 1
                    """
                )
            ).scalars().all()
        return list(rows)

    return await asyncio.to_thread(load)


@activity.defn
async def capture_company_fundamentals_activity(symbols: list[str], timeout: int, pause_seconds: float, skip_fresh: bool) -> dict[str, Any]:
    """Fetch and store each symbol's company page. With skip_fresh, symbols
    already fetched today are skipped (so a retried activity resumes). One
    symbol failing never fails the batch; the summary lists them."""
    cfg = load_app_config().database
    if skip_fresh:
        with session_scope(cfg) as s:
            fresh = set(s.execute(
                text("SELECT DISTINCT symbol FROM market_fundamental_daily WHERE scraped_at >= :d AND symbol = ANY(:syms)"),
                {"d": datetime.combine(_today_npt(), datetime.min.time()), "syms": symbols},
            ).scalars().all())
        symbols = [sym for sym in symbols if sym not in fresh]

    written, actions = 0, 0
    not_found: list[str] = []
    failed: list[str] = []
    for i, symbol in enumerate(symbols):
        activity.heartbeat({"symbol": symbol, "done": i, "of": len(symbols)})
        try:
            data = await asyncio.to_thread(fetch_company_fundamentals, symbol, timeout)
        except FundamentalsNotFound:
            not_found.append(symbol)
            continue
        except Exception as e:  # noqa: BLE001 - one page must not sink the batch
            activity.logger.warning(f"[fundamentals] {symbol}: {e}")
            failed.append(symbol)
            await asyncio.sleep(pause_seconds)
            continue
        row = {**data, "trade_date": data.get("last_traded_on") or _today_npt()}

        def store() -> int:
            with session_scope(cfg) as s:
                upsert_fundamentals_daily(s, [row])
                return replace_corporate_actions(s, symbol, data["history"])

        actions += await asyncio.to_thread(store)
        written += 1
        await asyncio.sleep(pause_seconds)
    return {"rows": written, "corporate_actions": actions, "not_found": not_found, "failed": failed,
            "attempted": len(symbols)}
