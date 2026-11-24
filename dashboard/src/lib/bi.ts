import { API_BASE } from "./api";

// Categorical series colours for the BI charts, in fixed order (never
// cycled). Validated with the dataviz palette validator on the panel
// surface #0f172a (dark): lightness band, chroma, adjacent CVD dE >= 8.4,
// normal-vision dE >= 19.3, contrast >= 3:1; the first three also pass
// all-pairs (scatter-like use).
export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"];
// Reserved status colours: direction (up/down), warnings. Never a series slot.
export const STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" };
// Diverging poles (polarity: net buy/sell, histogram above/below zero).
export const DIVERGING = { positive: "#3987e5", negative: "#e66767", neutral: "#383835" };

export const RECOMMENDATION_LABEL = {
  strong_buy: "Strong buy",
  buy: "Buy",
  hold: "Hold",
  sell: "Sell",
  strong_sell: "Strong sell",
};

// Tailwind classes per recommendation: text + border + background (with an
// arrow glyph in the badge itself, so it never relies on colour alone).
export const RECOMMENDATION_STYLE = {
  strong_buy: "border-emerald-400/60 bg-emerald-500/15 text-emerald-200",
  buy: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  hold: "border-slate-500/60 bg-slate-700/30 text-slate-200",
  sell: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  strong_sell: "border-rose-400/60 bg-rose-500/15 text-rose-200",
};

export const RECOMMENDATION_ICON = { strong_buy: "▲▲", buy: "▲", hold: "◆", sell: "▼", strong_sell: "▼▼" };

export const DIRECTION_STYLE = {
  bullish: { cls: "text-emerald-300", icon: "▲" },
  bearish: { cls: "text-rose-300", icon: "▼" },
  neutral: { cls: "text-slate-300", icon: "●" },
};

export const SEVERITY_STYLE = {
  info: { cls: "border-sky-500/40 text-sky-200", icon: "ℹ" },
  warning: { cls: "border-amber-400/50 text-amber-200", icon: "⚠" },
  critical: { cls: "border-rose-500/60 text-rose-200", icon: "⛔" },
};

export async function apiJson(path: string, method = "GET", body: unknown = undefined) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : `Request failed (${res.status})`;
    const error = new Error(message) as Error & { status?: number };
    error.status = res.status;
    throw error;
  }
  return data;
}

// POST /bi/ask and read its Server-Sent Events: delta {text}, tool {name,
// label, state}, done {...}, error {message}. EventSource can't POST, so the
// stream is parsed by hand.
export async function askStream(body, onEvent, signal?: AbortSignal) {
  const res = await fetch(`${API_BASE}/bi/ask`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      /* not JSON */
    }
    const error = new Error(message) as Error & { status?: number };
    error.status = res.status;
    throw error;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const data = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith(":")) continue; // keepalive comment
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (data.length) {
        try {
          onEvent(event, JSON.parse(data.join("\n")));
        } catch {
          /* ignore a malformed event */
        }
      }
    }
  }
}

// Zip a report's parallel chart arrays into recharts rows: {date, close, ...}.
export function rows(dates: string[] | undefined, columns: Record<string, (number | null)[] | undefined>): Record<string, any>[] {
  return (dates || []).map((date, i) => {
    const row: Record<string, any> = { date };
    for (const [key, values] of Object.entries(columns)) {
      if (values) row[key] = values[i] ?? null;
    }
    return row;
  });
}

export function signedPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function num(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}
