"""LLM access for the agents through the generic OpenAI-compatible Chat
Completions API (`openai` library): OpenAI, or any compatible server set
with BI_LLM_BASE_URL (Ollama, vLLM, LM Studio, OpenRouter, Azure, ...).

  LLM.json()  one structured-output request (report synthesis, news
              sentiment, portfolio notes). Asks for the JSON schema
              (response_format json_schema), stepping down to JSON mode and
              then to schema-in-the-prompt when a server rejects the
              stricter form; the reply is parsed and checked either way.
  LLM.chat()  the Q&A loop: streamed answer with function tools the master
              agent routes to the specialist agents, at most MAX_TOOL_TURNS.

Without a model (and an API key or base URL) `enabled` is False and the
agents fall back to rule-based output.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from nepse_common.config import BiConfig

log = logging.getLogger("bi.llm")

MAX_TOOL_TURNS = 8
JSON_MODES = ("json_schema", "json_object", "none")


class LLMError(Exception):
    pass


@dataclass
class Tool:
    """A function tool for LLM.chat: JSON schema from a pydantic model (also
    used to validate the model's arguments) and the async handler."""

    name: str
    description: str
    model: type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[str]]
    label: Callable[[BaseModel], str]

    def spec(self) -> dict[str, Any]:
        schema = self.model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": schema}}


def _parse_json(text: str) -> dict[str, Any]:
    """The reply's JSON object, tolerating ```json fences or prose around it."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def _conform(data: Any, schema: dict[str, Any]) -> Any:
    """Coerce a parsed reply onto the schema: fill missing required keys with
    empty values, drop unknown keys, clamp enum values, cast numbers."""
    t = schema.get("type")
    if "enum" in schema:
        return data if data in schema["enum"] else schema["enum"][len(schema["enum"]) // 2]
    if t == "object":
        data = data if isinstance(data, dict) else {}
        return {k: _conform(data.get(k), sub) for k, sub in schema.get("properties", {}).items()}
    if t == "array":
        return [_conform(x, schema.get("items", {})) for x in (data if isinstance(data, list) else [])]
    if t in ("number", "integer"):
        try:
            return int(data) if t == "integer" else float(data)
        except (TypeError, ValueError):
            return 0
    if t == "boolean":
        return bool(data)
    return "" if data is None else str(data)


class LLM:
    def __init__(self, cfg: BiConfig) -> None:
        self.model = cfg.llm_model
        self.enabled = cfg.llm_enabled
        self._json_mode = cfg.llm_json_mode if cfg.llm_json_mode in JSON_MODES else "json_schema"
        self._extra: dict[str, Any] = {}
        if cfg.llm_temperature is not None:
            self._extra["temperature"] = cfg.llm_temperature
        if cfg.llm_max_tokens:
            self._extra["max_tokens"] = cfg.llm_max_tokens
        self._client = (
            openai.AsyncOpenAI(api_key=cfg.llm_api_key or "not-needed", base_url=cfg.llm_base_url or None, max_retries=3, timeout=300.0)
            if self.enabled else None
        )

    def _require(self) -> openai.AsyncOpenAI:
        if self._client is None:
            raise LLMError("No LLM is configured (set BI_LLM_MODEL and BI_LLM_API_KEY or BI_LLM_BASE_URL)")
        return self._client

    async def json(self, *, system: str, content: str, schema: dict[str, Any], name: str = "result") -> tuple[dict[str, Any], dict[str, Any]]:
        client = self._require()
        instructions = (f"{system}\n\nReply with ONE JSON object only (no prose, no code fences) that follows this JSON schema:\n"
                        f"{json.dumps(schema)}")
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": content}]
        modes = JSON_MODES[JSON_MODES.index(self._json_mode):]
        last_error: Exception | None = None
        for mode in modes:
            kwargs: dict[str, Any] = dict(self._extra)
            if mode == "json_schema":
                kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
            elif mode == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            try:
                resp = await client.chat.completions.create(model=self.model, messages=messages, **kwargs)
            except openai.BadRequestError as e:  # this server doesn't take that response_format: step down
                log.info("response_format %s rejected (%s); stepping down", mode, e)
                last_error = e
                self._json_mode = JSON_MODES[min(JSON_MODES.index(mode) + 1, len(JSON_MODES) - 1)]
                continue
            choice = resp.choices[0]
            if getattr(choice.message, "refusal", None):
                raise LLMError(f"the model refused: {choice.message.refusal}")
            try:
                data = _conform(_parse_json(choice.message.content or ""), schema)
            except (ValueError, json.JSONDecodeError) as e:
                raise LLMError(f"the model did not return valid JSON: {e}") from e
            usage = resp.usage
            return data, {"model": resp.model or self.model, "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                          "output_tokens": getattr(usage, "completion_tokens", 0) or 0}
        raise LLMError(f"structured output failed: {last_error}")

    async def chat(self, *, system: str, messages: list[dict[str, Any]], tools: list[Tool]) -> AsyncIterator[dict[str, Any]]:
        """Yields {"type": "text", "text"}, {"type": "tool", "name", "label",
        "state"} and finally {"type": "done", usage..., "sources"}."""
        client = self._require()
        by_name = {t.name: t for t in tools}
        specs = [t.spec() for t in tools]
        convo: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        totals = {"input_tokens": 0, "output_tokens": 0}
        sources: list[str] = []
        model_used = self.model
        include_usage = True
        for turn in range(MAX_TOOL_TURNS + 1):
            kwargs: dict[str, Any] = dict(self._extra)
            if include_usage:
                kwargs["stream_options"] = {"include_usage": True}
            try:
                stream = await client.chat.completions.create(model=self.model, messages=convo, tools=specs, stream=True, **kwargs)
            except openai.BadRequestError:
                if not include_usage:
                    raise
                include_usage = False  # some servers reject stream_options
                stream = await client.chat.completions.create(model=self.model, messages=convo, tools=specs, stream=True, **dict(self._extra))
            text_parts: list[str] = []
            calls: dict[int, dict[str, str]] = {}
            finish = None
            async for chunk in stream:
                if getattr(chunk, "model", None):
                    model_used = chunk.model
                if getattr(chunk, "usage", None):
                    totals["input_tokens"] += chunk.usage.prompt_tokens or 0
                    totals["output_tokens"] += chunk.usage.completion_tokens or 0
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta and delta.content:
                    text_parts.append(delta.content)
                    yield {"type": "text", "text": delta.content}
                for tc in (delta.tool_calls or []) if delta else []:
                    slot = calls.setdefault(tc.index or 0, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
                finish = choice.finish_reason or finish
            if not calls:
                if finish == "length":
                    yield {"type": "text", "text": "\n\n_The answer was cut off (output limit)._"}
                break
            if turn == MAX_TOOL_TURNS:
                yield {"type": "text", "text": "\n\n_Stopped after the maximum number of data lookups._"}
                break
            ordered = [calls[i] for i in sorted(calls)]
            for i, c in enumerate(ordered):
                c["id"] = c["id"] or f"call_{turn}_{i}"
            convo.append({"role": "assistant", "content": "".join(text_parts) or None,
                          "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                                         for c in ordered]})
            for c in ordered:
                tool = by_name.get(c["name"])
                if tool is None:
                    convo.append({"role": "tool", "tool_call_id": c["id"], "content": f"Error: unknown tool {c['name']}"})
                    continue
                try:
                    args = tool.model.model_validate(json.loads(c["arguments"] or "{}"))
                except (json.JSONDecodeError, ValidationError) as e:
                    convo.append({"role": "tool", "tool_call_id": c["id"], "content": f"Error: invalid arguments ({e}); fix them and call again."})
                    continue
                label = tool.label(args)
                yield {"type": "tool", "name": tool.name, "label": label, "state": "running"}
                try:
                    out = await tool.handler(args)
                    sources.append(label)
                    yield {"type": "tool", "name": tool.name, "label": label, "state": "done"}
                except Exception as e:  # noqa: BLE001 - report the failure to the model, keep going
                    log.warning("tool %s failed: %s", tool.name, e)
                    out = f"Error: {e}"
                    yield {"type": "tool", "name": tool.name, "label": label, "state": "error"}
                convo.append({"role": "tool", "tool_call_id": c["id"], "content": out})
            yield {"type": "text", "text": ""}  # keeps the stream alive between rounds
        yield {"type": "done", "model": model_used, **totals, "sources": sources}
