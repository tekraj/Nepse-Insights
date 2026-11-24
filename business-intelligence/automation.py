"""Temporal side of the BI service (task queue bi-automation-queue):

  BiReportRefreshWorkflow  every BI_REPORT_SWEEP_MINUTES: regenerate the
                           reports that are due (missing, setup changed, or
                           older than the script's live/off-hours interval;
                           an unchanged input fingerprint skips the work).
  BiMonitorWorkflow        every BI_MONITOR_INTERVAL_MINUTES: price-move /
                           volume / news alerts, then refresh the reports of
                           the scripts that triggered one.
  BiReportWorkflow         one report on demand (gRPC RefreshReport, a saved
                           setup).

Every run writes a pipeline_run row (sources bi_report_refresh, bi_monitor,
bi_report_on_demand), like the other services' jobs.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from nepse_common.config import load_app_config

TASK_QUEUE = "bi-automation-queue"
_RETRY = RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=20))

# Set by main.py: the process-wide MasterAgent (holds the LLM client).
MASTER: Any = None


# ------------------------------------------------------------------ activities


@activity.defn
async def bi_due_reports_activity() -> list[str]:
    import market_data
    import store

    live = (await asyncio.to_thread(market_data.session_state))["live"]
    return await asyncio.to_thread(store.due_symbols, live)


@activity.defn
async def bi_generate_report_activity(symbol: str, force: bool, reason: str) -> dict[str, Any]:
    return await MASTER.generate(symbol, force=force, reason=reason)


@activity.defn
async def bi_check_alerts_activity() -> dict[str, Any]:
    import monitor
    import store

    result = await asyncio.to_thread(monitor.check_alerts)
    if datetime.now().minute == 0:  # hourly housekeeping
        await asyncio.to_thread(store.prune_notifications)
    return result


@activity.defn
async def bi_write_run_log_activity(log: dict[str, Any]) -> None:
    from nepse_common.db.session import session_scope
    from nepse_common.models import PipelineRun

    def write() -> None:
        with session_scope(load_app_config().database) as s:
            s.add(PipelineRun(
                status=log["status"], message=log.get("message"), error_text=log.get("error_text"), articles_found=0,
                articles_inserted=0, records_written=int(log.get("records") or 0), source=log["source"],
                started_at=datetime.fromisoformat(log["started_at"]), finished_at=datetime.fromisoformat(log["finished_at"]),
                duration_ms=int(log.get("duration_ms") or 0),
            ))

    await asyncio.to_thread(write)


ACTIVITIES = [bi_due_reports_activity, bi_generate_report_activity, bi_check_alerts_activity, bi_write_run_log_activity]


# ------------------------------------------------------------------ workflows


async def _log(started_at: datetime, source: str, status: str, message: str, records: int, error_text: str | None = None) -> None:
    finished = workflow.now()
    try:
        await workflow.execute_activity(
            bi_write_run_log_activity,
            {"status": status, "message": message, "error_text": error_text, "records": records, "source": source,
             # naive NPT like every other pipeline_run row
             "started_at": (started_at + timedelta(hours=5, minutes=45)).replace(tzinfo=None).isoformat(),
             "finished_at": (finished + timedelta(hours=5, minutes=45)).replace(tzinfo=None).isoformat(),
             "duration_ms": int((finished - started_at).total_seconds() * 1000)},
            start_to_close_timeout=timedelta(minutes=1), retry_policy=RetryPolicy(maximum_attempts=3),
        )
    except Exception as e:  # noqa: BLE001
        workflow.logger.error(f"[{source}] run log failed: {e}")


async def _generate_many(symbols: list[str], force: bool, reason: str, concurrency: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for start in range(0, len(symbols), max(1, concurrency)):
        batch = symbols[start:start + concurrency]
        outs = await asyncio.gather(*(
            workflow.execute_activity(bi_generate_report_activity, args=[s, force, reason],
                                      start_to_close_timeout=timedelta(minutes=15), retry_policy=_RETRY)
            for s in batch
        ), return_exceptions=True)
        for s, o in zip(batch, outs):
            results.append(o if isinstance(o, dict) else {"symbol": s, "status": "failed", "error": str(o)[:200]})
    return results


def _summary(results: list[dict[str, Any]]) -> tuple[str, int, list[str]]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    failed = [r["symbol"] for r in results if r["status"] == "failed"]
    generated = sum(v for k, v in counts.items() if k in ("ok", "partial"))
    msg = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "nothing due"
    return msg, generated, failed


@workflow.defn
class BiReportRefreshWorkflow:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        started = workflow.now()
        cfg = load_app_config().bi
        try:
            due = await workflow.execute_activity(bi_due_reports_activity, start_to_close_timeout=timedelta(minutes=1), retry_policy=_RETRY)
            results = await _generate_many(due, False, "schedule", cfg.report_concurrency)
            msg, generated, failed = _summary(results)
            await _log(started, "bi_report_refresh", "failed" if failed and not generated else "success",
                       msg + (f"; failed: {', '.join(failed)}" if failed else ""), generated)
            return {"due": due, "results": results}
        except Exception as e:  # noqa: BLE001
            await _log(started, "bi_report_refresh", "failed", "report refresh crashed", 0, str(e))
            raise


@workflow.defn
class BiMonitorWorkflow:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        started = workflow.now()
        cfg = load_app_config().bi
        try:
            alerts = await workflow.execute_activity(bi_check_alerts_activity, start_to_close_timeout=timedelta(minutes=3), retry_policy=_RETRY)
            results = await _generate_many(alerts["refresh"], False, "alert", cfg.report_concurrency) if alerts["refresh"] else []
            msg = f"{alerts['checked']} scripts watched, {alerts['alerts']} new alerts"
            if results:
                msg += f"; refreshed {', '.join(r['symbol'] for r in results)}"
            await _log(started, "bi_monitor", "success", msg, alerts["alerts"])
            return {"alerts": alerts, "results": results}
        except Exception as e:  # noqa: BLE001
            await _log(started, "bi_monitor", "failed", "monitor crashed", 0, str(e))
            raise


@workflow.defn
class BiReportWorkflow:
    @workflow.run
    async def run(self, symbol: str, force: bool = True, reason: str = "on_demand") -> dict[str, Any]:
        started = workflow.now()
        results = await _generate_many([symbol], force, reason, 1)
        r = results[0]
        await _log(started, "bi_report_on_demand", "failed" if r["status"] == "failed" else "success",
                   f"{symbol}: {r['status']}" + (f" ({r.get('recommendation')})" if r.get("recommendation") else "")
                   + (f" - {r.get('error')}" if r.get("error") else ""), 1 if r["status"] in ("ok", "partial") else 0)
        return r


WORKFLOWS = [BiReportRefreshWorkflow, BiMonitorWorkflow, BiReportWorkflow]


# ------------------------------------------------------------------ schedules

_NPT_PHASE = timedelta(hours=5, minutes=45)


def _every(interval: timedelta, second: int):
    from temporalio.client import ScheduleIntervalSpec, ScheduleSpec

    secs = int(interval.total_seconds())
    phase = int(_NPT_PHASE.total_seconds()) % secs
    offset = timedelta(0) if phase == 0 else interval - timedelta(seconds=phase)
    return ScheduleSpec(intervals=[ScheduleIntervalSpec(every=interval, offset=offset + timedelta(seconds=second))])


async def upsert_schedules(client: Any) -> None:
    """Idempotent create-or-update, same pattern as the other workers. The
    monitor fires at :45 of each minute, after nepse-service's scrapes
    (:05-:21) have landed; the refresh sweep at :30."""
    from temporalio.client import (Schedule, ScheduleActionStartWorkflow, ScheduleOverlapPolicy, SchedulePolicy,
                                   ScheduleUpdate)

    cfg = load_app_config().bi
    policy = SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP)
    specs = {
        "bi-report-refresh-schedule": (_every(timedelta(minutes=cfg.report_sweep_minutes), 30),
                                       ScheduleActionStartWorkflow(BiReportRefreshWorkflow.run, id="bi-report-refresh-workflow", task_queue=TASK_QUEUE)),
        "bi-monitor-schedule": (_every(timedelta(minutes=cfg.monitor_interval_minutes), 45),
                                ScheduleActionStartWorkflow(BiMonitorWorkflow.run, id="bi-monitor-workflow", task_queue=TASK_QUEUE)),
    }
    for schedule_id, (spec, action) in specs.items():
        schedule = Schedule(action=action, spec=spec, policy=policy)
        try:
            handle = client.get_schedule_handle(schedule_id)

            async def updater(_input: Any, schedule: Schedule = schedule) -> ScheduleUpdate:
                return ScheduleUpdate(schedule=schedule)

            await handle.update(updater)
        except Exception:
            try:
                await client.create_schedule(schedule_id, schedule)
            except Exception as e:
                if "already" not in str(e).lower():
                    raise


async def pause_schedules(client: Any, paused: bool) -> None:
    for schedule_id in ("bi-report-refresh-schedule", "bi-monitor-schedule"):
        try:
            handle = client.get_schedule_handle(schedule_id)
            await (handle.pause(note="BI_AUTOMATION_ENABLED=false") if paused else handle.unpause())
        except Exception:
            pass
