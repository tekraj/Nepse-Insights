import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { askStream } from "../../lib/bi";
import { MiniMarkdown } from "./MiniMarkdown";

const SUGGESTIONS = [
  "Should I buy, hold or sell now for a 3-month view?",
  "What are the main risks right now?",
  "How does it compare with its sector peers on valuation?",
  "Which brokers have been accumulating over the last month?",
  "Summarise the latest news and its likely impact.",
];

// Q&A with the BI master agent about one script. The answer streams in
// (SSE); the agent's data lookups show as chips while they run. The
// conversation is kept per script for this browser session.
export function ChatPanel({ symbol, llmEnabled }) {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef(null);
  const endRef = useRef(null);
  const messages = conversations[symbol] || [];

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  function update(fn) {
    setConversations((all) => ({ ...all, [symbol]: fn(all[symbol] || []) }));
  }

  async function ask(question) {
    const q = question.trim();
    if (!q || busy || !symbol) return;
    const history = messages.filter((m) => m.content && !m.error).map((m) => ({ role: m.role, content: m.content }));
    update((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", tools: [], streaming: true }]);
    setInput("");
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const patchLast = (fn) => update((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    try {
      await askStream({ symbol, question: q, history }, (event, data) => {
        if (event === "delta") patchLast((a) => ({ ...a, content: a.content + data.text }));
        else if (event === "tool")
          patchLast((a) => {
            const tools = a.tools.filter((t) => t.label !== data.label);
            return { ...a, tools: [...tools, data] };
          });
        else if (event === "done") patchLast((a) => ({ ...a, streaming: false, meta: data }));
        else if (event === "error") patchLast((a) => ({ ...a, streaming: false, error: data.message }));
      }, controller.signal);
    } catch (e) {
      if (e.status === 401) navigate("/login", { replace: true });
      else if (e.name !== "AbortError") patchLast((a) => ({ ...a, error: e.message }));
    } finally {
      patchLast((a) => ({ ...a, streaming: false }));
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-[420px] flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-display text-xl font-semibold">Ask about {symbol || "a script"}</h3>
        {messages.length ? (
          <button type="button" className="text-xs text-slate-400 hover:text-slate-200" onClick={() => update(() => [])} disabled={busy}>
            Clear
          </button>
        ) : null}
      </div>
      {!llmEnabled ? (
        <p className="mb-2 rounded-lg border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">
          No LLM is configured for the BI service (BI_LLM_MODEL / BI_LLM_API_KEY), so answers can't be generated yet.
        </p>
      ) : null}
      <div className="flex-1 space-y-3 overflow-y-auto pr-1" style={{ maxHeight: 560 }}>
        {!messages.length ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-400">
              Answers combine this script's report with live database lookups (prices, indicators, fundamentals, news, broker flows).
            </p>
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" disabled={busy || !symbol} onClick={() => ask(s)}
                className="block w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-left text-xs text-slate-300 hover:border-cyan-400/60">
                {s}
              </button>
            ))}
          </div>
        ) : null}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ml-6 rounded-xl bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100">{m.content}</div>
          ) : (
            <div key={i} className="mr-2 rounded-xl border border-slate-700/70 bg-slate-900/60 px-3 py-2">
              {m.tools?.length ? (
                <div className="mb-2 flex flex-wrap gap-1">
                  {m.tools.map((t) => (
                    <span key={t.label} className={`rounded-full border px-2 py-0.5 text-[11px] ${t.state === "error" ? "border-rose-500/50 text-rose-200" : t.state === "done" ? "border-slate-600 text-slate-400" : "border-cyan-400/50 text-cyan-200"}`}>
                      {t.state === "running" ? "⏳ " : t.state === "done" ? "✓ " : "✗ "}
                      {t.label}
                    </span>
                  ))}
                </div>
              ) : null}
              {m.content ? <MiniMarkdown text={m.content} /> : m.streaming ? <p className="text-sm text-slate-400">Thinking…</p> : null}
              {m.error ? <p className="mt-1 text-xs text-rose-300">⚠ {m.error}</p> : null}
              {m.meta?.model ? <p className="mt-1 text-[10px] text-slate-500">{m.meta.model} · {m.meta.input_tokens + m.meta.output_tokens} tokens</p> : null}
            </div>
          ),
        )}
        <div ref={endRef} />
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <input className="field flex-1 py-2 text-sm" placeholder={symbol ? `Ask about ${symbol}…` : "Select a script"} value={input}
          onChange={(e) => setInput(e.target.value)} disabled={!symbol} maxLength={4000} />
        {busy ? (
          <button type="button" className="btn-ghost px-3 py-2 text-sm" onClick={() => abortRef.current?.abort()}>Stop</button>
        ) : (
          <button type="submit" className="btn-primary px-3 py-2 text-sm" disabled={!input.trim() || !symbol}>Ask</button>
        )}
      </form>
      <p className="mt-1 text-[10px] text-slate-500">Research support, not financial advice.</p>
    </div>
  );
}
