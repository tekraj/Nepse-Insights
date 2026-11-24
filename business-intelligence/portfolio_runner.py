"""Runs portfolio optimisations in the background and fans their progress out
to listeners (the gRPC stream api-service turns into SSE).

One run per user at a time: a new request cancels that user's running one.
A run always finishes and saves its row in bi_portfolio, even when nobody is
listening any more (the user closed the page) -- the next visit shows it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from nepse_common.config import load_app_config
from nepse_common.db.session import session_scope
from nepse_common.models import BiPortfolio

from agents.portfolio import optimize_portfolio
from common import clean, now_npt
from llm import LLM

log = logging.getLogger("bi.portfolio")

NARRATIVE_SYSTEM = """You are a portfolio analyst for the Nepal Stock Exchange (NEPSE). An optimiser has built
a portfolio for an investor's budget, horizon and target return from quantitative analytics; you
receive its output as JSON. Explain it for the investor: why these scripts and weights, whether
the target return is realistic, and the main risks (use the risk analysis numbers exactly as given,
never invent figures). Prices are NPR. Research support, not personalised financial advice."""

NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Markdown, 2-3 short paragraphs."},
        "target_assessment": {"type": "string", "description": "Is the target return realistic over the horizon, and how likely?"},
        "risk_assessment": {"type": "string", "description": "The main risks in plain words, quoting VaR / drawdown / probabilities."},
        "rationale": {"type": "array", "items": {"type": "object", "properties": {"symbol": {"type": "string"}, "reason": {"type": "string"}},
                                                  "required": ["symbol", "reason"], "additionalProperties": False}},
        "suggestions": {"type": "array", "items": {"type": "string"}, "description": "How to adjust (target, horizon, risk) or monitor."},
    },
    "required": ["summary", "target_assessment", "risk_assessment", "rationale", "suggestions"],
    "additionalProperties": False,
}


def _save(user: str, **values: Any) -> dict[str, Any]:
    row = {"user_email": user, **values}
    with session_scope(load_app_config().database) as s:
        stmt = pg_insert(BiPortfolio).values(**row)
        stmt = stmt.on_conflict_do_update(index_elements=["user_email"], set_={k: stmt.excluded[k] for k in row if k != "user_email"})
        s.execute(stmt)
    return row


def load(user: str) -> dict[str, Any] | None:
    with session_scope(load_app_config().database) as s:
        row = s.get(BiPortfolio, user)
        return clean({c.name: getattr(row, c.name) for c in BiPortfolio.__table__.columns}) if row else None


def _rule_narrative(result: dict[str, Any]) -> dict[str, Any]:
    p, req = result["portfolio"], result["request"]
    reach = (f"The {req['target_return_pct']:.1f}% target over {req['horizon']} is reachable on the model's expectations "
             f"(expected {p['expected_return_pct']:.2f}%), with a {p['probability_reach_target_pct']:.0f}% simulated chance of reaching it."
             if p["target_reachable"] else
             f"The {req['target_return_pct']:.1f}% target over {req['horizon']} is above what the analytics support: the best expected "
             f"return under your caps is {p['max_achievable_return_pct']:.2f}%, so this is the maximum-return portfolio "
             f"({p['probability_reach_target_pct']:.0f}% simulated chance of reaching the target).")
    top = ", ".join(f"{a['symbol']} {a['weight_pct']:.0f}%" for a in result["allocations"][:5] if a["shares"] > 0)
    return {
        "summary": f"**Allocation:** {top or 'cash only'}; NPR {p['invested']:,.0f} invested, NPR {p['cash_left']:,.0f} left in cash.\n\n{reach}",
        "target_assessment": reach,
        "risk_assessment": (f"Volatility over the horizon {p['volatility_pct']:.1f}%; 95% VaR {p['var_95_pct']:.1f}% "
                            f"(NPR {p['var_95_amount']:,.0f}), CVaR {p['cvar_95_pct']:.1f}%; {p['probability_loss_pct']:.0f}% chance of a loss; "
                            f"typical max drawdown {p['expected_max_drawdown_pct']:.1f}%; beta {p['beta_nepse']:.2f} to NEPSE "
                            f"(a -10% NEPSE move ~ {p['nepse_minus_10_impact_pct']:.1f}%)."),
        "rationale": [{"symbol": a["symbol"], "reason": "; ".join(a["factors"][:3]) or "diversification / risk balance"}
                      for a in result["allocations"] if a["shares"] > 0],
        "suggestions": (["Lower the target or lengthen the horizon to reach a feasible, lower-risk portfolio."] if not p["target_reachable"] else [])
                       + ["Re-run after major news or a large market move; the allocation reflects today's analytics."],
    }


class PortfolioRun:
    def __init__(self, user: str, request: dict[str, Any]) -> None:
        self.user = user
        self.request = request
        self.events: list[dict[str, Any]] = []
        self.requested_at = now_npt()
        self.done = asyncio.Event()
        self._changed = asyncio.Condition()
        self.task: asyncio.Task | None = None

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        async with self._changed:
            self._changed.notify_all()

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        i = 0
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.done.is_set():
                return
            async with self._changed:
                await self._changed.wait_for(lambda: len(self.events) > i or self.done.is_set())


class PortfolioRunner:
    def __init__(self, llm: LLM) -> None:
        self.llm = llm
        self.runs: dict[str, PortfolioRun] = {}

    async def start(self, user: str, request: dict[str, Any]) -> PortfolioRun:
        old = self.runs.get(user)
        if old and old.task and not old.task.done():
            old.task.cancel()
        run = PortfolioRun(user, request)
        self.runs[user] = run
        await asyncio.to_thread(_save, user, status="running", request=request, result=None, error_text=None, llm_used=False,
                                llm_model=None, generation_ms=None, requested_at=run.requested_at, completed_at=None)
        run.task = asyncio.create_task(self._run(run))
        return run

    async def _run(self, run: PortfolioRun) -> None:
        started = time.monotonic()
        loop = asyncio.get_running_loop()

        def progress(stage: str, message: str, fraction: float) -> None:  # called from the worker thread
            asyncio.run_coroutine_threadsafe(run.emit({"type": "progress", "stage": stage, "message": message, "fraction": fraction}), loop)

        try:
            result = await asyncio.to_thread(optimize_portfolio, run.request, progress)
            llm_used, llm_model = False, None
            narrative = _rule_narrative(result)
            if self.llm.enabled:
                await run.emit({"type": "progress", "stage": "narrative", "message": "Writing the explanation", "fraction": 0.92})
                compact = {k: result[k] for k in ("request", "portfolio", "allocations", "sells", "sector_exposure", "assumptions")}
                compact["alternatives"] = {k: {kk: vv for kk, vv in v.items() if kk != "weights"} for k, v in result["alternatives"].items()}
                compact["risk"] = {k: result["risk"][k] for k in ("outcome_percentiles_pct",)} | {"historical_replay": {
                    k: v for k, v in result["risk"]["historical_replay"].items() if k not in ("dates", "cumulative_pct")}}
                try:
                    narrative, usage = await self.llm.json(system=NARRATIVE_SYSTEM, content=json.dumps(compact, default=str),
                                                           schema=NARRATIVE_SCHEMA, name="portfolio_explanation")
                    llm_used, llm_model = True, usage.get("model")
                except Exception as e:  # noqa: BLE001 - keep the rule-based narrative
                    log.warning("portfolio narrative failed: %s", e)
            result["narrative"] = narrative
            row = await asyncio.to_thread(
                _save, run.user, status="ok", request=run.request, result=clean(result), error_text=None, llm_used=llm_used,
                llm_model=llm_model, generation_ms=int((time.monotonic() - started) * 1000), requested_at=run.requested_at, completed_at=now_npt())
            await run.emit({"type": "result", "portfolio": clean(row)})
        except asyncio.CancelledError:
            await run.emit({"type": "error", "message": "Replaced by a newer optimisation request."})
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("portfolio optimisation failed for %s", run.user)
            msg = str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}"
            await asyncio.to_thread(_save, run.user, status="failed", request=run.request, result=None, error_text=msg[:1000],
                                    llm_used=False, llm_model=None, generation_ms=int((time.monotonic() - started) * 1000),
                                    requested_at=run.requested_at, completed_at=now_npt())
            await run.emit({"type": "error", "message": msg[:1000]})
        finally:
            run.done.set()
            async with run._changed:
                run._changed.notify_all()
