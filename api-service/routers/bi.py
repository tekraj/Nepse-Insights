"""Business-intelligence endpoints. Everything is forwarded over gRPC to the
business-intelligence service, which owns the bi_* tables.

  /admin/bi/catalog, /admin/bi/settings[/{symbol}]   BI Setup page
  /bi/reports[/{symbol}[/refresh]], /bi/ask (SSE), /bi/notifications   BI page + bell
  /bi/portfolio/optimize (SSE), /bi/portfolio                           Portfolio page
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import grpc
from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from deps import get_current_claims
from nepse_common.bi_grpc import business_intelligence_pb2 as pb
from services import bi_client
from services.bi_client import call

admin_router = APIRouter(dependencies=[Depends(get_current_claims)])
router = APIRouter(dependencies=[Depends(get_current_claims)])

_KEEPALIVE_SECONDS = 10  # SSE comment while the agent thinks / runs tools, so proxies keep the stream open


def _sym(symbol: str) -> str:
    return symbol.strip().upper()


# ------------------------------------------------------------------ admin: setup


@admin_router.get("/catalog")
async def bi_catalog() -> dict[str, Any]:
    resp = await call("GetCatalog", pb.GetCatalogRequest())
    return json.loads(resp.catalog_json)


@admin_router.get("/settings")
async def bi_settings() -> dict[str, Any]:
    resp = await call("ListSettings", pb.ListSettingsRequest())
    return {"settings": [bi_client.setting_json(s) for s in resp.settings]}


@admin_router.get("/settings/{symbol}")
async def bi_setting(symbol: str) -> dict[str, Any]:
    return bi_client.setting_json(await call("GetSetting", pb.SymbolRequest(symbol=_sym(symbol))))


@admin_router.put("/settings/{symbol}")
async def bi_save_setting(symbol: str, body: dict[str, Any] = Body(...), claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
    request = pb.UpsertSettingRequest(setting=bi_client.setting_proto(_sym(symbol), body), user=claims.get("sub") or "")
    return bi_client.setting_json(await call("UpsertSetting", request))


@admin_router.delete("/settings/{symbol}")
async def bi_delete_setting(symbol: str) -> dict[str, Any]:
    resp = await call("DeleteSetting", pb.SymbolRequest(symbol=_sym(symbol)))
    return {"deleted": resp.deleted}


# ------------------------------------------------------------------ reports


@router.get("/reports")
async def bi_reports() -> dict[str, Any]:
    resp = await call("ListReports", pb.ListReportsRequest())
    return {"reports": [bi_client.summary_json(r) for r in resp.reports], "llm_enabled": resp.llm_enabled}


@router.get("/reports/{symbol}")
async def bi_report(symbol: str) -> dict[str, Any]:
    resp = await call("GetReport", pb.SymbolRequest(symbol=_sym(symbol)))
    return {"summary": bi_client.summary_json(resp.summary), "exists": resp.exists,
            "report": json.loads(resp.report_json) if resp.report_json else None}


@router.post("/reports/{symbol}/refresh")
async def bi_refresh(symbol: str) -> dict[str, Any]:
    resp = await call("RefreshReport", pb.SymbolRequest(symbol=_sym(symbol)))
    return {"queued": resp.queued, "workflow_id": resp.workflow_id, "message": resp.message}


# ------------------------------------------------------------------ Q&A (Server-Sent Events)


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=20000)


class AskBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    question: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _relay(stream, convert) -> StreamingResponse:
    """Turn a server-streaming gRPC call into Server-Sent Events. `convert`
    maps each message to (event, data) or None. A comment line goes out
    every few seconds while the agent works, so proxies keep the stream open."""

    async def events():
        iterator = stream.__aiter__()
        pending = asyncio.ensure_future(iterator.__anext__())
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=_KEEPALIVE_SECONDS)
                if not done:
                    yield b": keepalive\n\n"
                    continue
                try:
                    msg = pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.ensure_future(iterator.__anext__())
                out = convert(msg)
                if out:
                    yield _sse(*out)
        except grpc.aio.AioRpcError as e:
            yield _sse("error", {"message": bi_client.http_error(e).detail})
        finally:
            if not pending.done():
                pending.cancel()
            stream.cancel()

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _ask_event(ev):
    kind = ev.WhichOneof("event")
    if kind == "text_delta":
        return "delta", {"text": ev.text_delta}
    if kind == "tool":
        return "tool", {"name": ev.tool.name, "label": ev.tool.label, "state": ev.tool.state}
    if kind == "done":
        return "done", {"model": ev.done.model, "input_tokens": ev.done.input_tokens, "output_tokens": ev.done.output_tokens,
                        "sources": list(ev.done.sources)}
    if kind == "error":
        return "error", {"message": ev.error}
    return None


@router.post("/ask")
async def bi_ask(body: AskBody, claims: dict[str, Any] = Depends(get_current_claims)) -> StreamingResponse:
    """Streams the master agent's answer as SSE: `delta` {text}, `tool`
    {name, label, state}, `done` {model, tokens, sources}, `error` {message}."""
    request = pb.AskRequest(symbol=_sym(body.symbol), question=body.question, user=claims.get("sub") or "",
                            history=[pb.ChatTurn(role=t.role, content=t.content) for t in body.history])
    return _relay(bi_client.stub().Ask(request, timeout=600), _ask_event)


# ------------------------------------------------------------------ portfolio (SSE)


def _portfolio_event(ev):
    kind = ev.WhichOneof("event")
    if kind == "progress":
        return "progress", {"stage": ev.progress.stage, "message": ev.progress.message, "fraction": ev.progress.fraction}
    if kind == "portfolio_json":
        return "result", {"portfolio": json.loads(ev.portfolio_json)}
    if kind == "error":
        return "error", {"message": ev.error}
    return None


@router.post("/portfolio/optimize")
async def bi_portfolio_optimize(body: dict[str, Any] = Body(...), claims: dict[str, Any] = Depends(get_current_claims)) -> StreamingResponse:
    """Run the portfolio agent for the signed-in user (budget, horizon,
    target_return_pct, risk_profile, ...): SSE `progress` {stage, message,
    fraction} events, then `result` {portfolio} or `error` {message}. The
    result is cached per user (GET /bi/portfolio) even if this stream drops."""
    request = pb.PortfolioRequest(user=claims.get("sub") or "", request_json=json.dumps(body))
    return _relay(bi_client.stub().OptimizePortfolio(request, timeout=900), _portfolio_event)


@router.get("/portfolio")
async def bi_portfolio(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
    """The signed-in user's latest optimisation (status running/ok/failed)."""
    resp = await call("GetPortfolio", pb.PortfolioQuery(user=claims.get("sub") or ""))
    return {"exists": resp.exists, "portfolio": json.loads(resp.portfolio_json) if resp.portfolio_json else None}


# ------------------------------------------------------------------ notifications


@router.get("/notifications")
async def bi_notifications(
    symbol: str = Query(default="", max_length=20),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict[str, Any]:
    resp = await call("ListNotifications", pb.ListNotificationsRequest(symbol=_sym(symbol), unread_only=unread_only, limit=limit))
    return {"notifications": [bi_client.notification_json(n) for n in resp.notifications], "unread_count": resp.unread_count}


class MarkReadBody(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=500)
    all: bool = False
    symbol: str = ""


@router.post("/notifications/read")
async def bi_mark_read(body: MarkReadBody) -> dict[str, Any]:
    resp = await call("MarkNotificationsRead", pb.MarkNotificationsReadRequest(ids=body.ids, all=body.all, symbol=_sym(body.symbol)))
    return {"updated": resp.updated}
