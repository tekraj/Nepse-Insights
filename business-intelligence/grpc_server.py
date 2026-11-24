"""gRPC servicer (nepse.bi.v1.BusinessIntelligence) used by api-service."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import grpc
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError

from nepse_common.bi_grpc import business_intelligence_pb2 as pb
from nepse_common.bi_grpc import business_intelligence_pb2_grpc as pb_grpc

import automation
import catalog
import market_data
import portfolio_runner
import store
from agents.master import MasterAgent
from agents.portfolio import validate_request as validate_portfolio_request
from common import clean

log = logging.getLogger("bi.grpc")

_SCALARS = ("enabled", "horizon", "risk_profile", "price_basis", "lookback_days", "refresh_minutes_live", "refresh_minutes_offhours",
            "technical_enabled", "fundamental_enabled", "news_enabled", "quant_enabled", "alerts_enabled", "alert_price_change_pct",
            "alert_volume_spike_ratio", "alert_on_signal_change", "alert_on_news", "llm_summary_enabled")


def _iso(v: Any) -> str:
    return v.isoformat(timespec="seconds") if hasattr(v, "isoformat") else (v or "")


def setting_pb(d: dict[str, Any], info: dict[str, Any] | None = None) -> pb.Setting:
    return pb.Setting(
        symbol=d["symbol"], **{k: d[k] for k in _SCALARS},
        features_json=json.dumps(clean(d["features"])), news_keywords=list(d.get("news_keywords") or []),
        custom_instructions=d.get("custom_instructions") or "", created_at=_iso(d.get("created_at")),
        updated_at=_iso(d.get("updated_at")), updated_by=d.get("updated_by") or "",
        company_name=(info or {}).get("company_name") or "", sector=(info or {}).get("sector_name") or "",
    )


def setting_from_pb(m: pb.Setting) -> dict[str, Any]:
    try:
        features = json.loads(m.features_json) if m.features_json else {}
    except json.JSONDecodeError as e:
        raise ValueError(f"features_json is not valid JSON: {e}") from e
    return {"symbol": m.symbol, **{k: getattr(m, k) for k in _SCALARS}, "features": features,
            "news_keywords": list(m.news_keywords), "custom_instructions": m.custom_instructions}


def summary_pb(r: dict[str, Any]) -> pb.ReportSummary:
    return pb.ReportSummary(
        symbol=r["symbol"], company_name=r.get("company_name") or "", sector=r.get("sector") or "", enabled=bool(r.get("enabled", True)),
        status=r.get("status") or "missing", recommendation=r.get("recommendation") or "", score=float(r.get("score") or 0),
        confidence=float(r.get("confidence") or 0), headline=r.get("headline") or "", last_price=float(r.get("last_price") or 0),
        generated_at=_iso(r.get("generated_at")), data_as_of=_iso(r.get("data_as_of")),
    )


class BusinessIntelligenceServicer(pb_grpc.BusinessIntelligenceServicer):
    def __init__(self, master: MasterAgent, temporal: Client, portfolios: portfolio_runner.PortfolioRunner) -> None:
        self.master = master
        self.temporal = temporal
        self.portfolios = portfolios

    async def _start_report(self, symbol: str, reason: str) -> pb.RefreshReportResponse:
        wf_id = f"bi-report-{symbol}"
        try:
            await self.temporal.start_workflow(
                automation.BiReportWorkflow.run, args=[symbol, True, reason], id=wf_id, task_queue=automation.TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            )
            return pb.RefreshReportResponse(queued=True, workflow_id=wf_id, message="Report regeneration started.")
        except RPCError as e:
            if "already" in str(e).lower():
                return pb.RefreshReportResponse(queued=False, workflow_id=wf_id, message="A regeneration is already running.")
            raise

    # ----------------------------------------------------------- catalog/settings

    async def GetCatalog(self, request, context):  # noqa: N802
        data = catalog.catalog()
        defaults = store.default_setting("")
        defaults.pop("symbol")
        data["defaults"] = defaults
        data["llm_enabled"] = self.master.llm.enabled
        data["llm_model"] = self.master.llm.model
        return pb.Catalog(catalog_json=json.dumps(clean(data)))

    async def ListSettings(self, request, context):  # noqa: N802
        rows = await asyncio.to_thread(store.list_settings)
        info = await asyncio.to_thread(market_data.securities_info, [r["symbol"] for r in rows])
        return pb.ListSettingsResponse(settings=[setting_pb(r, info.get(r["symbol"])) for r in rows])

    async def GetSetting(self, request, context):  # noqa: N802
        symbol = request.symbol.strip().upper()
        row = await asyncio.to_thread(store.get_setting, symbol)
        if row is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"{symbol} is not set up")
        return setting_pb(row, await asyncio.to_thread(market_data.security_info, symbol))

    async def UpsertSetting(self, request, context):  # noqa: N802
        try:
            raw = setting_from_pb(request.setting)
            saved = await asyncio.to_thread(store.upsert_setting, raw, request.user or None)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        if saved["enabled"]:
            try:
                await self._start_report(saved["symbol"], "setup_saved")
            except Exception as e:  # noqa: BLE001 - the sweep picks it up anyway
                log.warning("could not start report for %s: %s", saved["symbol"], e)
        return setting_pb(saved, await asyncio.to_thread(market_data.security_info, saved["symbol"]))

    async def DeleteSetting(self, request, context):  # noqa: N802
        return pb.DeleteSettingResponse(deleted=await asyncio.to_thread(store.delete_setting, request.symbol.strip().upper()))

    # ------------------------------------------------------------------- reports

    async def ListReports(self, request, context):  # noqa: N802
        rows = await asyncio.to_thread(store.report_summaries)
        return pb.ListReportsResponse(reports=[summary_pb(r) for r in rows], llm_enabled=self.master.llm.enabled)

    async def GetReport(self, request, context):  # noqa: N802
        symbol = request.symbol.strip().upper()
        setting = await asyncio.to_thread(store.get_setting, symbol)
        if setting is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"{symbol} is not set up")
        report = await asyncio.to_thread(store.get_report, symbol)
        info = await asyncio.to_thread(market_data.security_info, symbol) or {}
        base = {"symbol": symbol, "enabled": setting["enabled"], "company_name": info.get("company_name"), "sector": info.get("sector_name")}
        if report is None:
            return pb.Report(summary=summary_pb({**base, "status": "missing"}), exists=False, report_json="")
        body = {**report, "company_name": info.get("company_name"), "sector": info.get("sector_name"),
                "setting": {k: setting[k] for k in ("horizon", "risk_profile", "price_basis", "lookback_days", "features",
                                                    "technical_enabled", "fundamental_enabled", "news_enabled", "quant_enabled",
                                                    "llm_summary_enabled", "refresh_minutes_live", "refresh_minutes_offhours")}}
        return pb.Report(summary=summary_pb({**base, **report}), exists=True, report_json=json.dumps(clean(body), default=str))

    async def RefreshReport(self, request, context):  # noqa: N802
        symbol = request.symbol.strip().upper()
        if await asyncio.to_thread(store.get_setting, symbol) is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"{symbol} is not set up")
        return await self._start_report(symbol, "manual")

    # ----------------------------------------------------------------------- Q&A

    async def Ask(self, request, context):  # noqa: N802
        symbol = request.symbol.strip().upper()
        question = request.question.strip()
        if not symbol or not question:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "symbol and question are required")
        if len(question) > 4000:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "question too long (max 4000 characters)")
        history = [{"role": t.role, "content": t.content} for t in request.history]
        try:
            async for ev in self.master.answer(symbol, question, history):
                if ev["type"] == "text":
                    if ev["text"]:
                        yield pb.AskEvent(text_delta=ev["text"])
                elif ev["type"] == "tool":
                    yield pb.AskEvent(tool=pb.ToolStatus(name=ev["name"], label=ev["label"], state=ev["state"]))
                elif ev["type"] == "done":
                    yield pb.AskEvent(done=pb.AskDone(model=ev.get("model") or "", input_tokens=ev.get("input_tokens", 0),
                                                      output_tokens=ev.get("output_tokens", 0), sources=ev.get("sources", [])))
        except Exception as e:  # noqa: BLE001 - surface to the client as an event
            log.exception("ask failed for %s", symbol)
            yield pb.AskEvent(error=f"{type(e).__name__}: {e}"[:500])

    # ---------------------------------------------------------------- portfolio

    async def OptimizePortfolio(self, request, context):  # noqa: N802
        user = request.user.strip().lower()
        if not user:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user is required")
        try:
            req = validate_portfolio_request(json.loads(request.request_json or "{}"))
        except (ValueError, json.JSONDecodeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        run = await self.portfolios.start(user, req)
        yield pb.PortfolioEvent(progress=pb.PortfolioProgress(stage="queued", message="Portfolio agent started", fraction=0.01))
        async for ev in run.listen():
            if ev["type"] == "progress":
                yield pb.PortfolioEvent(progress=pb.PortfolioProgress(stage=ev["stage"], message=ev["message"], fraction=ev["fraction"]))
            elif ev["type"] == "result":
                yield pb.PortfolioEvent(portfolio_json=json.dumps(ev["portfolio"], default=str))
            elif ev["type"] == "error":
                yield pb.PortfolioEvent(error=ev["message"])

    async def GetPortfolio(self, request, context):  # noqa: N802
        row = await asyncio.to_thread(portfolio_runner.load, request.user.strip().lower())
        return pb.PortfolioResult(exists=row is not None, portfolio_json=json.dumps(row, default=str) if row else "")

    # ------------------------------------------------------------- notifications

    async def ListNotifications(self, request, context):  # noqa: N802
        rows, unread = await asyncio.to_thread(store.list_notifications, request.symbol.strip().upper() or None,
                                               request.unread_only, request.limit or 50)
        return pb.ListNotificationsResponse(unread_count=unread, notifications=[
            pb.Notification(id=r["id"], symbol=r.get("symbol") or "", kind=r["kind"], severity=r["severity"], title=r["title"],
                            body=r.get("body") or "", data_json=json.dumps(r.get("data") or {}), created_at=_iso(r.get("created_at")),
                            read=r.get("read_at") is not None)
            for r in rows])

    async def MarkNotificationsRead(self, request, context):  # noqa: N802
        n = await asyncio.to_thread(store.mark_notifications_read, list(request.ids), request.all, request.symbol.strip().upper() or None)
        return pb.MarkNotificationsReadResponse(updated=n)
