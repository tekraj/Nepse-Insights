"""Shared types for the specialist agents.

Every agent takes an AgentContext and returns a *section* dict:

  {agent, status: ok|no_data|failed, summary, score (-100..100 or None),
   signals: [{id, label, direction: bullish|bearish|neutral, strength 0..1,
              value, detail}],
   metrics: {...}, charts: {...}, data: {...}, features: [ids], error}

The score is the strength-weighted vote of the agent's directional
signals; the master agent blends the four scores (weights depend on the
setting's horizon) and hands the sections to the LLM for the synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from common import clean, now_npt

DIRECTION_SIGN = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}


@dataclass
class AgentContext:
    symbol: str
    setting: dict[str, Any]
    info: dict[str, Any]
    session: dict[str, Any]
    llm: Any | None = None
    previous: dict[str, Any] | None = None  # the current bi_report row (for reuse/caching)
    now: datetime = field(default_factory=now_npt)

    def features(self, group: str) -> dict[str, dict[str, Any]]:
        return self.setting.get(f"{group}_features") or {}


def signal(sid: str, label: str, direction: str, strength: float, value: Any = None, detail: str = "",
           weight: float = 1.0) -> dict[str, Any]:
    return {"id": sid, "label": label, "direction": direction, "strength": round(max(0.0, min(1.0, strength)), 3),
            "value": value, "detail": detail, "weight": weight}


def score_signals(signals: list[dict[str, Any]]) -> float | None:
    """Strength-weighted vote of the directional signals, -100..100."""
    directional = [s for s in signals if s["direction"] != "neutral"]
    if not directional:
        return 0.0 if signals else None
    num = sum(DIRECTION_SIGN[s["direction"]] * s["strength"] * s.get("weight", 1.0) for s in directional)
    den = sum(s.get("weight", 1.0) for s in signals)
    return max(-100.0, min(100.0, 100.0 * num / den)) if den else None


def section(agent: str, status: str, *, summary: str = "", score: float | None = None,
            signals: list[dict[str, Any]] | None = None, metrics: dict[str, Any] | None = None,
            charts: dict[str, Any] | None = None, data: dict[str, Any] | None = None,
            features: list[str] | None = None, error: str | None = None) -> dict[str, Any]:
    return clean({
        "agent": agent, "status": status, "summary": summary, "score": score, "signals": signals or [],
        "metrics": metrics or {}, "charts": charts or {}, "data": data or {}, "features": features or [],
        "error": error, "generated_at": now_npt(),
    })


def top_signals_text(signals: list[dict[str, Any]], n: int = 4) -> str:
    ranked = sorted((s for s in signals if s["direction"] != "neutral"), key=lambda s: -s["strength"])[:n]
    return "; ".join(f"{s['label']} ({s['direction']})" for s in ranked)


def fmt_price(v: float | None) -> str:
    return "-" if v is None else f"{v:,.2f}"


def fmt_pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return "-"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"
