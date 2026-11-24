from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from nepse_common.config import load_app_config

    from activities.fundamentals_activities import (
        capture_company_fundamentals_activity,
        fundamentals_due_activity,
        fundamentals_symbols_activity,
    )
    from workflows.run_log import write_run_log

_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=30))
_BATCH = 40  # symbols per activity: ~2-3 minutes of paced requests


@workflow.defn
class CompanyFundamentalsWorkflow:
    """Daily after the close (register_schedules.py) and once on worker
    startup: every active equity's company page on merolagani ->
    market_fundamental_daily (EPS, P/E, book value, P/BV, dividend, market
    cap per session) + market_corporate_action (dividend/bonus/right
    history). Skips days without a session unless forced or the table is
    stale. Feeds the business-intelligence fundamental agent."""

    @workflow.run
    async def run(self, force: bool = False) -> dict[str, Any]:
        cfg = load_app_config().scraper
        started_at = workflow.now()
        status, error_text, rows = "success", None, 0
        try:
            due = await workflow.execute_activity(
                fundamentals_due_activity, args=[force], start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY
            )
            if not due["due"]:
                message = f"skipped: {due['reason']}"
            else:
                symbols = await workflow.execute_activity(
                    fundamentals_symbols_activity, start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY
                )
                not_found: list[str] = []
                failed: list[str] = []
                actions = 0
                for start in range(0, len(symbols), _BATCH):
                    batch = symbols[start:start + _BATCH]
                    try:
                        result = await workflow.execute_activity(
                            capture_company_fundamentals_activity,
                            args=[batch, cfg.request_timeout, cfg.merolagani_request_pause_seconds, not force],
                            start_to_close_timeout=timedelta(minutes=30),
                            heartbeat_timeout=timedelta(minutes=3),
                            retry_policy=_RETRY,
                        )
                        rows += result["rows"]
                        actions += result["corporate_actions"]
                        not_found += result["not_found"]
                        failed += result["failed"]
                    except Exception:  # noqa: BLE001 - one batch must not sink the rest
                        failed += batch
                message = f"{rows} companies ({due['reason']}), {actions} dividend/bonus/right rows"
                if not_found:
                    message += f"; no merolagani page: {len(not_found)}"
                if failed:
                    message += f"; failed: {', '.join(failed[:20])}{' ...' if len(failed) > 20 else ''}"
                    if not rows:
                        status = "failed"
        except Exception as e:  # noqa: BLE001
            status, message, error_text = "failed", "fundamentals capture crashed", str(e)

        await write_run_log(started_at, status=status, message=message, error_text=error_text, records=rows,
                            source="merolagani_fundamentals")
        return {"status": status, "rows": rows, "message": message}
