"""Database access for the BI tables: bi_setting (validated against the
catalog), bi_report (one row per script, overwritten) and bi_notification."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nepse_common.config import load_app_config
from nepse_common.db.session import session_scope
from nepse_common.models import BiNotification, BiReport, BiSetting

import catalog
import market_data
from common import clean, now_npt

GROUPS = catalog.GROUP_IDS
SETTING_FIELDS = (
    "enabled", "horizon", "risk_profile", "price_basis", "lookback_days", "refresh_minutes_live", "refresh_minutes_offhours",
    "technical_enabled", "fundamental_enabled", "news_enabled", "quant_enabled", "news_keywords", "alerts_enabled",
    "alert_price_change_pct", "alert_volume_spike_ratio", "alert_on_signal_change", "alert_on_news", "llm_summary_enabled",
    "custom_instructions",
)


def _session():
    return session_scope(load_app_config().database)


# --------------------------------------------------------------------------
# Settings


def setting_to_dict(row: BiSetting) -> dict[str, Any]:
    d = {c: getattr(row, c) for c in ("symbol", *SETTING_FIELDS, "created_at", "updated_at", "updated_by")}
    d["features"] = {g: getattr(row, f"{g}_features") or {} for g in GROUPS}
    for g in GROUPS:
        d[f"{g}_features"] = d["features"][g]
    d["alert_price_change_pct"] = float(d["alert_price_change_pct"])
    d["alert_volume_spike_ratio"] = float(d["alert_volume_spike_ratio"])
    return d


def list_settings() -> list[dict[str, Any]]:
    with _session() as s:
        rows = s.execute(select(BiSetting).order_by(BiSetting.symbol)).scalars().all()
        return [setting_to_dict(r) for r in rows]


def get_setting(symbol: str) -> dict[str, Any] | None:
    with _session() as s:
        row = s.get(BiSetting, symbol)
        return setting_to_dict(row) if row else None


def default_setting(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol, "enabled": True, "horizon": "medium", "risk_profile": "moderate", "price_basis": "adjusted",
        "lookback_days": 365, "refresh_minutes_live": 15, "refresh_minutes_offhours": 240,
        "technical_enabled": True, "fundamental_enabled": True, "news_enabled": True, "quant_enabled": True,
        "features": catalog.default_features(), "news_keywords": [], "alerts_enabled": True, "alert_price_change_pct": 3.0,
        "alert_volume_spike_ratio": 3.0, "alert_on_signal_change": True, "alert_on_news": True, "llm_summary_enabled": True,
        "custom_instructions": None,
    }


def validate_setting(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a setup from the dashboard; raises ValueError (shown to the user)."""
    symbol = (raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    info = market_data.security_info(symbol)
    if info is None:
        raise ValueError(f"Unknown script {symbol}")
    if info.get("instrument_type") != "Equity":
        raise ValueError(f"{symbol} is a {info.get('instrument_type')}, not an equity")
    if not market_data.has_daily_history(symbol):
        raise ValueError(f"{symbol} has no daily price history yet")
    base = default_setting(symbol)
    out: dict[str, Any] = {"symbol": symbol}
    for k in SETTING_FIELDS:
        out[k] = raw.get(k, base[k]) if raw.get(k) is not None else base[k]
    for k, allowed in catalog.GENERAL.items():
        if out[k] not in allowed:
            raise ValueError(f"{k} must be one of {', '.join(allowed)}")
    for k, lo, hi in (("lookback_days", 30, 3650), ("refresh_minutes_live", 5, 240), ("refresh_minutes_offhours", 15, 1440)):
        out[k] = int(out[k])
        if not lo <= out[k] <= hi:
            raise ValueError(f"{k} must be between {lo} and {hi}")
    for k, lo, hi in (("alert_price_change_pct", 0.5, 10), ("alert_volume_spike_ratio", 1.2, 20)):
        out[k] = float(out[k])
        if not lo <= out[k] <= hi:
            raise ValueError(f"{k} must be between {lo} and {hi}")
    for k in ("enabled", "technical_enabled", "fundamental_enabled", "news_enabled", "quant_enabled", "alerts_enabled",
              "alert_on_signal_change", "alert_on_news", "llm_summary_enabled"):
        out[k] = bool(out[k])
    keywords = out["news_keywords"] or []
    if isinstance(keywords, str):
        keywords = keywords.split(",")
    out["news_keywords"] = [k.strip() for k in keywords if k and k.strip() and len(k.strip()) >= 2][:10]
    out["custom_instructions"] = (out["custom_instructions"] or "").strip()[:2000] or None
    features = raw.get("features") or base["features"]
    for g in GROUPS:
        out[f"{g}_features"] = catalog.normalize_features(g, features.get(g) or {})
    if not any(out[f"{g}_enabled"] for g in GROUPS):
        raise ValueError("enable at least one analysis")
    return out


def upsert_setting(raw: dict[str, Any], user: str | None) -> dict[str, Any]:
    values = validate_setting(raw)
    values["updated_by"] = user
    values["updated_at"] = now_npt()
    with _session() as s:
        stmt = pg_insert(BiSetting).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["symbol"], set_={k: stmt.excluded[k] for k in values if k != "symbol"})
        s.execute(stmt)
    return get_setting(values["symbol"])


def delete_setting(symbol: str) -> bool:
    with _session() as s:
        return bool(s.execute(delete(BiSetting).where(BiSetting.symbol == symbol)).rowcount)


# --------------------------------------------------------------------------
# Reports


def report_to_dict(row: BiReport) -> dict[str, Any]:
    return clean({c.name: getattr(row, c.name) for c in BiReport.__table__.columns})


def get_report(symbol: str) -> dict[str, Any] | None:
    with _session() as s:
        row = s.get(BiReport, symbol)
        return report_to_dict(row) if row else None


def save_report(values: dict[str, Any]) -> None:
    with _session() as s:
        stmt = pg_insert(BiReport).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["symbol"], set_={k: stmt.excluded[k] for k in values if k != "symbol"})
        s.execute(stmt)


def report_summaries() -> list[dict[str, Any]]:
    """Every configured script with its report's headline fields (no body)."""
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT st.symbol, st.enabled, r.status, r.recommendation, r.score, r.confidence, r.headline, r.last_price,
                       r.generated_at, r.data_as_of
                FROM bi_setting st LEFT JOIN bi_report r ON r.symbol = st.symbol ORDER BY st.symbol
                """
            )
        ).mappings().all()
    info = market_data.securities_info([r["symbol"] for r in rows])
    return [clean({**dict(r), "status": r["status"] or "missing", "company_name": (info.get(r["symbol"]) or {}).get("company_name"),
                   "sector": (info.get(r["symbol"]) or {}).get("sector_name")}) for r in rows]


def due_symbols(live: bool, limit: int = 50) -> list[str]:
    """Enabled scripts whose report is missing, older than the setup, or
    older than its refresh interval (live / off-hours), stalest first."""
    interval = "refresh_minutes_live" if live else "refresh_minutes_offhours"
    with _session() as s:
        rows = s.execute(
            text(
                f"""
                SELECT st.symbol FROM bi_setting st LEFT JOIN bi_report r ON r.symbol = st.symbol
                WHERE st.enabled AND (r.symbol IS NULL OR r.generated_at < st.updated_at
                      OR r.generated_at < now()::timestamp - make_interval(mins => st.{interval}))
                ORDER BY r.generated_at NULLS FIRST LIMIT :limit
                """
            ),
            {"limit": limit},
        ).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------
# Notifications


def add_notification(symbol: str | None, kind: str, severity: str, title: str, body: str | None, data: dict[str, Any],
                     dedupe_key: str) -> bool:
    """Insert unless an alert with the same dedupe_key exists. True if new."""
    with _session() as s:
        stmt = pg_insert(BiNotification).values(symbol=symbol, kind=kind, severity=severity, title=title, body=body,
                                                data=clean(data), dedupe_key=dedupe_key)
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"]).returning(BiNotification.id)
        return s.execute(stmt).first() is not None


def list_notifications(symbol: str | None, unread_only: bool, limit: int) -> tuple[list[dict[str, Any]], int]:
    with _session() as s:
        q = select(BiNotification).order_by(BiNotification.created_at.desc(), BiNotification.id.desc()).limit(max(1, min(limit, 200)))
        cnt = select(func.count()).select_from(BiNotification).where(BiNotification.read_at.is_(None))
        if symbol:
            q = q.where(BiNotification.symbol == symbol)
            cnt = cnt.where(BiNotification.symbol == symbol)
        if unread_only:
            q = q.where(BiNotification.read_at.is_(None))
        rows = s.execute(q).scalars().all()
        unread = int(s.execute(cnt).scalar() or 0)
        return [clean({c.name: getattr(r, c.name) for c in BiNotification.__table__.columns}) for r in rows], unread


def mark_notifications_read(ids: list[int], all_: bool, symbol: str | None) -> int:
    with _session() as s:
        stmt = update(BiNotification).where(BiNotification.read_at.is_(None)).values(read_at=now_npt())
        if all_:
            if symbol:
                stmt = stmt.where(BiNotification.symbol == symbol)
        elif ids:
            stmt = stmt.where(BiNotification.id.in_(ids))
        else:
            return 0
        return int(s.execute(stmt).rowcount or 0)


def prune_notifications(keep_days: int = 90) -> int:
    with _session() as s:
        return int(s.execute(delete(BiNotification).where(BiNotification.created_at < now_npt() - timedelta(days=keep_days))).rowcount or 0)


def last_generated(symbol: str) -> datetime | None:
    with _session() as s:
        return s.execute(select(BiReport.generated_at).where(BiReport.symbol == symbol)).scalar()
