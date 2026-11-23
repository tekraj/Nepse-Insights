from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from nepse_common.models import PipelineRun
from nepse_common.schemas.util import to_iso

# Minute workflows log a success row with this message prefix on every tick
# outside market hours -- by far most rows, and not a run that did anything.
_SKIPPED_PREFIX = "market closed"

# pipeline_run.source names the source a run *used*, not the job:
# the live index job logs nepalstock_official / nepsetrading_* / merolagani_*
# depending on which fallback answered, and "none" when it skipped -- which
# is also what news-scraper runs log. Map rows to jobs for the health view.
_JOB_SQL = """
CASE
  WHEN message LIKE 'market closed - nepse%' OR source = 'nepalstock_official'
       OR source LIKE 'nepsetrading%'
       OR (source LIKE 'merolagani%' AND source <> 'merolagani_floor_sheet_history')
    THEN 'live_index'
  WHEN source = 'none' OR source IS NULL THEN 'news_scraper'
  ELSE source
END
"""

_JOB_LABELS = {
    "live_index": "Live index (17 indices)",
    "nepalstock_today_price": "Live prices",
    "nepalstock_floor_sheet": "Live trades",
    "nepalstock_sector_summary": "Sector summary",
    "nepalstock_market_depth": "Order book",
    "nepalstock_floor_sheet_eod": "Post-close trade sweep",
    "research_end_of_day": "End-of-day bars",
    "research_history_backfill": "Research history backfill",
    "merolagani_floor_sheet_history": "Broker history backfill",
    "news_scraper": "News scraper",
}


def _log_dict(r: PipelineRun) -> dict[str, Any]:
    # Response keys keep their original names (the dashboard reads them).
    return {
        "id": r.id,
        "status": r.status,
        "message": r.message,
        "error_text": r.error_text,
        "news_total": int(r.articles_found or 0),
        "news_inserted": int(r.articles_inserted or 0),
        "nepse_records": int(r.records_written or 0),
        "nepse_source": r.source,
        "started_at": to_iso(r.started_at),
        "finished_at": to_iso(r.finished_at),
        "duration_ms": int(r.duration_ms or 0),
        "created_at": to_iso(r.created_at),
    }


class PipelineLogService:
    """Pipeline run log queries against nepse_common.models.PipelineRun."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_recent_logs(
        self, limit: int, status: str = "all", source: str = "", include_skipped: bool = True
    ) -> dict[str, Any]:
        """Matches old GET /dashboard/pipeline-logs, plus filters: status
        (all/success/failed), an exact source, and hiding the
        market-closed skip rows."""
        stmt = select(PipelineRun)
        if status in ("success", "failed"):
            stmt = stmt.where(PipelineRun.status == status)
        if source:
            stmt = stmt.where(PipelineRun.source == source)
        if not include_skipped:
            stmt = stmt.where(
                or_(PipelineRun.message.is_(None), ~PipelineRun.message.startswith(_SKIPPED_PREFIX))
            )
        stmt = stmt.order_by(PipelineRun.started_at.desc().nulls_last(), PipelineRun.id.desc()).limit(limit)
        logs = [_log_dict(r) for r in self._db.execute(stmt).scalars().all()]

        success = sum(1 for item in logs if item["status"] == "success")
        failed = sum(1 for item in logs if item["status"] != "success")

        return {
            "total": len(logs),
            "summary": {
                "success": success,
                "failed": failed,
                "last_run_at": logs[0]["started_at"] if logs else None,
            },
            "logs": logs,
        }

    def get_sources(self) -> list[str]:
        rows = self._db.execute(
            text(
                """
                SELECT DISTINCT source FROM pipeline_run
                WHERE started_at >= now() - interval '30 days' AND source IS NOT NULL
                ORDER BY 1
                """
            )
        ).all()
        return [r.source for r in rows]

    def get_health(self, hours: int) -> dict[str, Any]:
        """Per job over the last `hours`: runs that did work, skips, failures,
        the last run / last productive success / last failure and its error,
        and which sources answered (the live index falls back from the
        official API to nepsetrading/merolagani)."""
        rows = self._db.execute(
            text(
                f"""
                WITH w AS (
                    SELECT *, {_JOB_SQL} AS job,
                           coalesce(status = 'success' AND message LIKE '{_SKIPPED_PREFIX}%', false) AS skipped
                    FROM pipeline_run
                    WHERE started_at >= now() - make_interval(hours => :hours)
                )
                SELECT job,
                       count(*) FILTER (WHERE status = 'success' AND NOT skipped) AS ok,
                       count(*) FILTER (WHERE skipped) AS skipped,
                       count(*) FILTER (WHERE status <> 'success') AS failed,
                       max(started_at) AS last_run,
                       max(started_at) FILTER (WHERE status = 'success' AND NOT skipped) AS last_ok,
                       max(started_at) FILTER (WHERE status <> 'success') AS last_failed,
                       (array_agg(coalesce(error_text, message) ORDER BY started_at DESC)
                           FILTER (WHERE status <> 'success'))[1] AS last_error,
                       sum(records_written) FILTER (WHERE status = 'success') AS records,
                       sum(articles_inserted) FILTER (WHERE status = 'success') AS news_inserted
                FROM w GROUP BY job
                """
            ),
            {"hours": hours},
        ).all()
        sources = self._db.execute(
            text(
                f"""
                SELECT {_JOB_SQL} AS job, source, count(*) AS runs
                FROM pipeline_run
                WHERE started_at >= now() - make_interval(hours => :hours)
                  AND status = 'success' AND coalesce(message, '') NOT LIKE '{_SKIPPED_PREFIX}%'
                GROUP BY 1, 2
                """
            ),
            {"hours": hours},
        ).all()
        by_job: dict[str, dict[str, int]] = {}
        for s in sources:
            by_job.setdefault(s.job, {})[s.source or "none"] = int(s.runs)

        # Longest silence between consecutive runs of a job (skips count as
        # runs). The minute jobs log every minute around the clock, so a long
        # gap means the stack or the machine was down -- e.g. the laptop
        # sleeping 2026-11-05 18:39 .. 11-06 03:08 -- which no failure row
        # would ever show.
        gaps = {
            r.job: r
            for r in self._db.execute(
                text(
                    f"""
                    SELECT DISTINCT ON (job) job, gap, started_at FROM (
                        SELECT {_JOB_SQL} AS job, started_at,
                               started_at - lag(started_at) OVER (PARTITION BY {_JOB_SQL} ORDER BY started_at) AS gap
                        FROM pipeline_run
                        WHERE started_at >= now() - make_interval(hours => :hours)
                    ) g
                    WHERE gap IS NOT NULL
                    ORDER BY job, gap DESC
                    """
                ),
                {"hours": hours},
            ).all()
        }

        jobs = [
            {
                "job": r.job,
                "label": _JOB_LABELS.get(r.job, r.job),
                "ok": int(r.ok or 0),
                "skipped": int(r.skipped or 0),
                "failed": int(r.failed or 0),
                "last_run": to_iso(r.last_run),
                "last_ok": to_iso(r.last_ok),
                "last_failed": to_iso(r.last_failed),
                "last_error": r.last_error,
                "records": int(r.records or 0),
                "news_inserted": int(r.news_inserted or 0),
                "sources": by_job.get(r.job, {}),
                "max_gap_minutes": gaps[r.job].gap.total_seconds() / 60 if r.job in gaps else None,
                "max_gap_ended_at": to_iso(gaps[r.job].started_at) if r.job in gaps else None,
            }
            for r in rows
        ]
        order = list(_JOB_LABELS)
        jobs.sort(key=lambda j: order.index(j["job"]) if j["job"] in order else len(order))
        return {"hours": hours, "jobs": jobs}
