"""gRPC client of the business-intelligence service (nepse.bi.v1).

One lazily created channel per process (BI_GRPC_ADDRESS, default
business-intelligence:50051). gRPC status codes map to HTTP errors so the
routers can just `await call(...)`.
"""
from __future__ import annotations

import json
from typing import Any

import grpc
from fastapi import HTTPException, status

from nepse_common.bi_grpc import business_intelligence_pb2 as pb
from nepse_common.bi_grpc import business_intelligence_pb2_grpc as pb_grpc
from nepse_common.config import load_app_config

_MAX_MESSAGE = 64 * 1024 * 1024
_channel: grpc.aio.Channel | None = None
_stub: pb_grpc.BusinessIntelligenceStub | None = None

_HTTP = {
    grpc.StatusCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    grpc.StatusCode.INVALID_ARGUMENT: status.HTTP_422_UNPROCESSABLE_ENTITY,
    grpc.StatusCode.UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED: status.HTTP_504_GATEWAY_TIMEOUT,
}


def stub() -> pb_grpc.BusinessIntelligenceStub:
    global _channel, _stub
    if _stub is None:
        _channel = grpc.aio.insecure_channel(
            load_app_config().bi.grpc_address,
            options=[("grpc.max_receive_message_length", _MAX_MESSAGE), ("grpc.max_send_message_length", _MAX_MESSAGE)],
        )
        _stub = pb_grpc.BusinessIntelligenceStub(_channel)
    return _stub


def http_error(e: grpc.aio.AioRpcError) -> HTTPException:
    code = _HTTP.get(e.code(), status.HTTP_502_BAD_GATEWAY)
    detail = e.details() or e.code().name
    if e.code() == grpc.StatusCode.UNAVAILABLE:
        detail = "The business-intelligence service is not reachable."
    return HTTPException(status_code=code, detail=detail)


async def call(method: str, request: Any, timeout: float = 30.0) -> Any:
    try:
        return await getattr(stub(), method)(request, timeout=timeout)
    except grpc.aio.AioRpcError as e:
        raise http_error(e) from e


# ------------------------------------------------------------------ JSON <-> proto

SETTING_SCALARS = ("enabled", "horizon", "risk_profile", "price_basis", "lookback_days", "refresh_minutes_live", "refresh_minutes_offhours",
                   "technical_enabled", "fundamental_enabled", "news_enabled", "quant_enabled", "alerts_enabled", "alert_price_change_pct",
                   "alert_volume_spike_ratio", "alert_on_signal_change", "alert_on_news", "llm_summary_enabled")


def setting_json(m: pb.Setting) -> dict[str, Any]:
    return {
        "symbol": m.symbol, **{k: getattr(m, k) for k in SETTING_SCALARS},
        "features": json.loads(m.features_json) if m.features_json else {},
        "news_keywords": list(m.news_keywords), "custom_instructions": m.custom_instructions or None,
        "created_at": m.created_at or None, "updated_at": m.updated_at or None, "updated_by": m.updated_by or None,
        "company_name": m.company_name or None, "sector": m.sector or None,
    }


def setting_proto(symbol: str, body: dict[str, Any]) -> pb.Setting:
    """The dashboard sends the whole setup; missing keys would silently
    become proto defaults (false / 0), so they are rejected here."""
    missing = [k for k in SETTING_SCALARS if k not in body]
    if missing:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"missing fields: {', '.join(missing)}")
    try:
        return pb.Setting(
            symbol=symbol, **{k: body[k] for k in SETTING_SCALARS},
            features_json=json.dumps(body.get("features") or {}), news_keywords=[str(k) for k in body.get("news_keywords") or []],
            custom_instructions=body.get("custom_instructions") or "",
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid setup: {e}") from e


def summary_json(m: pb.ReportSummary) -> dict[str, Any]:
    return {
        "symbol": m.symbol, "company_name": m.company_name or None, "sector": m.sector or None, "enabled": m.enabled,
        "status": m.status, "recommendation": m.recommendation or None, "score": m.score if m.status != "missing" else None,
        "confidence": m.confidence if m.status != "missing" else None, "headline": m.headline or None,
        "last_price": m.last_price or None, "generated_at": m.generated_at or None, "data_as_of": m.data_as_of or None,
    }


def notification_json(m: pb.Notification) -> dict[str, Any]:
    return {"id": m.id, "symbol": m.symbol or None, "kind": m.kind, "severity": m.severity, "title": m.title, "body": m.body or None,
            "data": json.loads(m.data_json) if m.data_json else {}, "created_at": m.created_at, "read": m.read}
