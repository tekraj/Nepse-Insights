import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { dispose, init } from "klinecharts";
import { AppShell } from "../components/AppShell";
import { NavLinks } from "../components/NavLinks";
import { Notice } from "../components/Panel";
import { SecurityPicker } from "../components/SecurityPicker";
import { TopBar } from "../components/TopBar";
import { apiRequest } from "../lib/api";
import { formatCompact, formatNumber, formatPct, trendColor } from "../lib/format";
import { useApi, useLogout } from "../lib/useApi";

// Candlestick chart with drawing tools (KLineChart) for positional trading:
// hourly candles for entries, daily/weekly/monthly for the trend. Bars come
// from /dashboard/candles (nepse_intraday_tick for 1H, the daily tables
// otherwise, plus today's live scrapes while a session runs).
const TIMEFRAMES = [
  { value: "1h", label: "1H", title: "Hourly candles (4 per session)" },
  { value: "1d", label: "1D", title: "Daily candles" },
  { value: "1w", label: "1W", title: "Weekly candles" },
  { value: "1M", label: "1M", title: "Monthly candles" },
];

const MAIN_INDICATORS = ["MA", "EMA", "BOLL"];
const SUB_INDICATORS = ["VOL", "MACD", "RSI"];

const TOOLS = [
  { name: "segment", glyph: "╱", label: "Trend line" },
  { name: "rayLine", glyph: "↗", label: "Ray" },
  { name: "straightLine", glyph: "⟋", label: "Extended line" },
  { name: "horizontalStraightLine", glyph: "―", label: "Horizontal line (support / resistance; shown on every timeframe)" },
  { name: "horizontalRayLine", glyph: "→", label: "Horizontal ray" },
  { name: "verticalStraightLine", glyph: "│", label: "Vertical line" },
  { name: "priceLine", glyph: "⊢", label: "Price line" },
  { name: "parallelStraightLine", glyph: "∥", label: "Parallel channel" },
  { name: "priceChannelLine", glyph: "⫽", label: "Price channel" },
  { name: "fibonacciLine", glyph: "Fib", label: "Fibonacci retracement" },
  { name: "simpleAnnotation", glyph: "✎", label: "Text note" },
];

// Horizontal lines are price levels, so they follow the symbol across
// timeframes; everything else is anchored to bars of one timeframe.
const SHARED_TOOLS = new Set(["horizontalStraightLine"]);
const LIVE_REFRESH_MS = 60000;

const UP = "#34d399";
const DOWN = "#f87171";
const TEXT = "#94a3b8";
const LINE = "rgba(148, 163, 184, .16)";

const CHART_STYLES = {
  grid: { horizontal: { color: LINE }, vertical: { color: LINE } },
  candle: {
    bar: {
      upColor: UP,
      downColor: DOWN,
      noChangeColor: TEXT,
      upBorderColor: UP,
      downBorderColor: DOWN,
      noChangeBorderColor: TEXT,
      upWickColor: UP,
      downWickColor: DOWN,
      noChangeWickColor: TEXT,
    },
    priceMark: {
      high: { color: "#e2e8f0" },
      low: { color: "#e2e8f0" },
      last: { upColor: UP, downColor: DOWN, noChangeColor: TEXT },
    },
    tooltip: { text: { color: "#cbd5e1" } },
  },
  indicator: { tooltip: { text: { color: "#cbd5e1" } } },
  xAxis: { axisLine: { color: LINE }, tickLine: { color: LINE }, tickText: { color: TEXT } },
  yAxis: { axisLine: { color: LINE }, tickLine: { color: LINE }, tickText: { color: TEXT } },
  separator: { color: "rgba(148, 163, 184, .3)" },
  crosshair: {
    horizontal: { line: { color: TEXT }, text: { backgroundColor: "#334155", borderColor: "#334155" } },
    vertical: { line: { color: TEXT }, text: { backgroundColor: "#334155", borderColor: "#334155" } },
  },
};

function storageKey(selected, scope) {
  return `nepse-candles:drawings:${selected.kind}:${selected.id}:${scope}`;
}

// Per-viewer convenience only: unavailable storage (private window, blocked
// site data) just means drawings aren't remembered.
function loadDrawings(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key) || "[]");
  } catch {
    return [];
  }
}

function storeDrawings(key, drawings) {
  try {
    window.localStorage.setItem(key, JSON.stringify(drawings));
  } catch {
    // ignore
  }
}

export function CandlesPage() {
  const navigate = useNavigate();
  const onLogout = useLogout();
  const [params, setParams] = useSearchParams();
  const stockParam = params.get("stock");
  const selected = stockParam ? { kind: "stock", id: stockParam.toUpperCase() } : { kind: "index", id: params.get("index") || "NEPSE" };
  const tfParam = params.get("tf");
  const tf = TIMEFRAMES.some((t) => t.value === tfParam) ? tfParam : "1d";
  const isStock = selected.kind === "stock";

  const [basis, setBasis] = useState("adjusted");
  const [mainIndicators, setMainIndicators] = useState(["MA"]);
  const [subIndicators, setSubIndicators] = useState(["VOL"]);
  const [activeTool, setActiveTool] = useState(null);
  const [magnet, setMagnet] = useState(true);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const indices = useApi("/dashboard/indices");

  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const subPanesRef = useRef(new Map());
  const overlaysRef = useRef(new Map()); // overlay id -> storage scope ("shared" | tf)
  const selectedOverlayRef = useRef(null);
  const contextRef = useRef({ selected, tf });
  const suppressSaveRef = useRef(false);
  contextRef.current = { selected, tf };

  // ---- chart lifecycle -------------------------------------------------
  useEffect(() => {
    const el = containerRef.current;
    const chart = init(el, { locale: "en-US", timezone: "Asia/Kathmandu", styles: CHART_STYLES });
    if (!chart) return undefined;
    chart.setPriceVolumePrecision(2, 0);
    chart.setBarSpace(9);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      dispose(el);
      chartRef.current = null;
      subPanesRef.current = new Map();
    };
  }, []);

  // ---- indicators ------------------------------------------------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const name of MAIN_INDICATORS) {
      const shown = Boolean(chart.getIndicatorByPaneId("candle_pane", name));
      if (mainIndicators.includes(name) && !shown) chart.createIndicator(name, true, { id: "candle_pane" });
      if (!mainIndicators.includes(name) && shown) chart.removeIndicator("candle_pane", name);
    }
  }, [mainIndicators]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const panes = subPanesRef.current;
    for (const name of SUB_INDICATORS) {
      if (subIndicators.includes(name) && !panes.has(name)) {
        const paneId = chart.createIndicator(name, false, { height: 110 });
        if (paneId) panes.set(name, paneId);
      }
      if (!subIndicators.includes(name) && panes.has(name)) {
        chart.removeIndicator(panes.get(name), name);
        panes.delete(name);
      }
    }
  }, [subIndicators]);

  // ---- drawings --------------------------------------------------------
  function saveDrawings() {
    const chart = chartRef.current;
    if (!chart || suppressSaveRef.current) return;
    const { selected: sel, tf: frame } = contextRef.current;
    const byScope = { shared: [], [frame]: [] };
    for (const [id, scope] of overlaysRef.current) {
      const overlay = chart.getOverlayById(id);
      if (!overlay || overlay.currentStep !== -1) continue; // still being drawn
      byScope[scope].push({
        name: overlay.name,
        points: overlay.points.map((p) => ({ timestamp: p.timestamp, value: p.value })),
        extendData: overlay.extendData ?? null,
      });
    }
    storeDrawings(storageKey(sel, "shared"), byScope.shared);
    storeDrawings(storageKey(sel, frame), byScope[frame]);
  }

  function addOverlay(name, points = null, extendData = null) {
    const chart = chartRef.current;
    if (!chart) return null;
    const scope = SHARED_TOOLS.has(name) ? "shared" : contextRef.current.tf;
    const id = chart.createOverlay({
      name,
      ...(points ? { points } : {}),
      ...(extendData !== null ? { extendData } : {}),
      mode: magnet ? "weak_magnet" : "normal",
      onDrawEnd: () => {
        setActiveTool(null);
        saveDrawings();
        return false;
      },
      onPressedMoveEnd: () => {
        saveDrawings();
        return false;
      },
      onRemoved: (event) => {
        overlaysRef.current.delete(event.overlay.id);
        if (selectedOverlayRef.current === event.overlay.id) selectedOverlayRef.current = null;
        saveDrawings();
        return false;
      },
      onSelected: (event) => {
        selectedOverlayRef.current = event.overlay.id;
        return false;
      },
      onDeselected: () => {
        selectedOverlayRef.current = null;
        return false;
      },
    });
    if (typeof id === "string") overlaysRef.current.set(id, scope);
    return id;
  }

  function restoreDrawings() {
    const chart = chartRef.current;
    if (!chart) return;
    const bars = chart.getDataList();
    const lastTs = bars.length ? bars[bars.length - 1].timestamp : null;
    for (const scope of ["shared", tf]) {
      for (const d of loadDrawings(storageKey(selected, scope))) {
        // A shared horizontal line only needs its price; re-anchor it to a
        // bar of this timeframe.
        const points = scope === "shared" && lastTs ? d.points.map((p) => ({ ...p, timestamp: lastTs })) : d.points;
        addOverlay(d.name, points, d.extendData);
      }
    }
  }

  function clearOverlaysFromChart() {
    const chart = chartRef.current;
    if (!chart) return;
    suppressSaveRef.current = true;
    chart.removeOverlay();
    overlaysRef.current = new Map();
    selectedOverlayRef.current = null;
    suppressSaveRef.current = false;
  }

  function startTool(tool) {
    if (tool.name === "simpleAnnotation") {
      const text = window.prompt("Note text");
      if (!text) return;
      addOverlay(tool.name, null, text);
    } else {
      addOverlay(tool.name);
    }
    setActiveTool(tool.name);
  }

  function clearDrawings() {
    if (!window.confirm(`Remove every drawing on ${selected.id} (this timeframe and the shared horizontal lines)?`)) return;
    clearOverlaysFromChart();
    storeDrawings(storageKey(selected, "shared"), []);
    storeDrawings(storageKey(selected, tf), []);
  }

  // Delete / Backspace removes the selected drawing; Escape cancels a tool.
  useEffect(() => {
    function onKey(e) {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(e.target?.tagName);
      if (typing) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selectedOverlayRef.current) {
        chartRef.current?.removeOverlay(selectedOverlayRef.current);
        e.preventDefault();
      }
      if (e.key === "Escape" && activeTool) {
        const chart = chartRef.current;
        for (const [id] of overlaysRef.current) {
          const overlay = chart?.getOverlayById(id);
          if (overlay && overlay.currentStep !== -1) chart.removeOverlay(id);
        }
        setActiveTool(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeTool]);

  // ---- data ------------------------------------------------------------
  const base = `/dashboard/candles?kind=${selected.kind}&symbol=${encodeURIComponent(selected.id)}&tf=${tf}&basis=${basis}`;

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return undefined;
    let active = true;
    setLoading(true);
    setError("");
    clearOverlaysFromChart();
    setActiveTool(null);

    chart.setLoadDataCallback(({ type, data, callback }) => {
      if (type !== "forward" || !data) {
        callback([], false);
        return;
      }
      apiRequest(`${base}&limit=1000&before=${data.timestamp}`)
        .then((r) => callback(active ? r.bars : [], active ? r.more : false))
        .catch(() => callback([], false));
    });

    apiRequest(`${base}&limit=1000`)
      .then((r) => {
        if (!active) return;
        chart.applyNewData(r.bars, r.more);
        setMeta(r);
        restoreDrawings();
      })
      .catch((e) => {
        if (!active) return;
        if (e.status === 401) {
          navigate("/login", { replace: true });
          return;
        }
        chart.clearData();
        setMeta(null);
        setError(`Unable to load candles for ${selected.id} (${e.status || "network error"}).`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    // While a session runs, extend/update the newest candles every minute.
    const timer = window.setInterval(() => {
      apiRequest(`${base}&limit=3`)
        .then((r) => {
          if (!active) return;
          const list = chart.getDataList();
          const lastTs = list.length ? list[list.length - 1].timestamp : 0;
          for (const bar of r.bars) if (bar.timestamp >= lastTs) chart.updateData(bar);
        })
        .catch(() => {});
    }, LIVE_REFRESH_MS);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  function select(kind, id) {
    setParams(kind === "stock" ? { stock: id, tf } : { index: id, tf });
  }

  function setTimeframe(value) {
    setParams(isStock ? { stock: selected.id, tf: value } : { index: selected.id, tf: value });
  }

  function toggle(list, setList, name) {
    setList(list.includes(name) ? list.filter((n) => n !== name) : [...list, name]);
  }

  const bars = meta?.bars || [];
  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  const change = last && prev ? ((last.close - prev.close) / prev.close) * 100 : null;
  const firstTs = bars.length ? bars[0].timestamp : null;
  // Per-stock 1H history before the live scrapes (2026-09-23) is still
  // being downloaded for most symbols.
  const thinIntraday = isStock && tf === "1h" && meta && !meta.more && firstTs && firstTs >= Date.parse("2026-09-15T00:00:00+05:45");

  const buttonClass = (on) =>
    `rounded-lg border px-3 py-1.5 text-sm ${on ? "border-cyan-300 bg-cyan-500/20 text-cyan-200" : "border-slate-600 bg-slate-800/80 text-slate-200 hover:border-slate-400"}`;

  return (
    <AppShell
      title="Candlestick Analysis"
      subtitle="Hourly to monthly candles for any index or stock, with indicators and drawing tools for positional trading"
      actions={<TopBar onLogout={onLogout} rightLink={<NavLinks />} />}
    >
      {error ? <Notice tone="rose">{error}</Notice> : null}

      {/* relative z-20: each .panel's backdrop-blur is its own stacking
          context, so the search dropdown must sit in a raised one. */}
      <section className="panel relative z-20 mb-3 flex flex-wrap items-end gap-4">
        <SecurityPicker indices={indices.data?.indices} selected={selected} onSelect={select} />

        <div>
          <span className="mb-1 block text-xs uppercase tracking-widest text-slate-400">Timeframe</span>
          <div className="flex gap-1">
            {TIMEFRAMES.map((t) => (
              <button key={t.value} type="button" title={t.title} className={buttonClass(t.value === tf)} onClick={() => setTimeframe(t.value)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {isStock ? (
          <div>
            <span className="mb-1 block text-xs uppercase tracking-widest text-slate-400">Prices</span>
            <div className="flex gap-1">
              <button type="button" className={buttonClass(basis === "adjusted")} title="Bonus/right-adjusted: no artificial gaps on ex-dates" onClick={() => setBasis("adjusted")}>
                Adjusted
              </button>
              <button type="button" className={buttonClass(basis === "raw")} title="As traded: gaps down on every bonus/right ex-date" onClick={() => setBasis("raw")}>
                Raw
              </button>
            </div>
          </div>
        ) : null}

        <div>
          <span className="mb-1 block text-xs uppercase tracking-widest text-slate-400">Indicators</span>
          <div className="flex flex-wrap gap-1">
            {MAIN_INDICATORS.map((name) => (
              <button key={name} type="button" className={buttonClass(mainIndicators.includes(name))} onClick={() => toggle(mainIndicators, setMainIndicators, name)}>
                {name}
              </button>
            ))}
            <span className="mx-1 self-center text-slate-600">|</span>
            {SUB_INDICATORS.map((name) => (
              <button key={name} type="button" className={buttonClass(subIndicators.includes(name))} onClick={() => toggle(subIndicators, setSubIndicators, name)}>
                {name}
              </button>
            ))}
          </div>
        </div>

        <div className="ml-auto text-right">
          <div className="font-display text-2xl font-bold text-slate-100">{last ? formatNumber(last.close, 2) : loading ? "…" : "-"}</div>
          <div className={`text-sm ${trendColor(change)}`}>
            {change !== null ? `${formatPct(change, 2, true)} vs previous ${TIMEFRAMES.find((t) => t.value === tf)?.label} candle` : " "}
          </div>
        </div>
      </section>

      {thinIntraday ? (
        <Notice>
          Hourly candles for {selected.id} start on 2026-09-23 for now: they come from the live 1-minute scrapes, and the per-stock tick history back to 2018 is still
          downloading (alphabetically, about a day in total). Daily, weekly and monthly candles go back to listing.
        </Notice>
      ) : null}

      <section className="panel flex gap-3 p-3">
        {/* Drawing tools */}
        <div className="flex w-14 shrink-0 flex-col items-stretch gap-1" role="toolbar" aria-label="Drawing tools">
          {TOOLS.map((tool) => (
            <button
              key={tool.name}
              type="button"
              title={tool.label}
              aria-label={tool.label}
              onClick={() => startTool(tool)}
              className={`h-9 rounded-lg border text-base leading-none ${
                activeTool === tool.name ? "border-cyan-300 bg-cyan-500/20 text-cyan-200" : "border-slate-700 bg-slate-800/70 text-slate-200 hover:border-slate-400"
              }`}
            >
              {tool.glyph}
            </button>
          ))}
          <div className="my-1 border-t border-slate-700" />
          <button
            type="button"
            title={magnet ? "Magnet on: points snap to candle open/high/low/close" : "Magnet off: points stay where you click"}
            onClick={() => setMagnet(!magnet)}
            className={`h-9 rounded-lg border text-base ${magnet ? "border-cyan-300 bg-cyan-500/20 text-cyan-200" : "border-slate-700 bg-slate-800/70 text-slate-400"}`}
          >
            🧲
          </button>
          <button
            type="button"
            title="Remove all drawings for this symbol and timeframe"
            onClick={clearDrawings}
            className="h-9 rounded-lg border border-slate-700 bg-slate-800/70 text-base text-rose-300 hover:border-rose-400"
          >
            ✕
          </button>
        </div>

        <div className="relative min-w-0 flex-1">
          <div ref={containerRef} className="h-[72vh] min-h-[520px] w-full" />
          {loading ? <div className="absolute left-3 top-2 text-xs text-slate-400">Loading…</div> : null}
        </div>
      </section>

      <p className="mt-2 text-xs text-slate-400">
        Pick a tool on the left, then click the chart to place its points (Escape cancels). Click a drawing to select it, drag to move it, press Delete to remove it.
        Drawings are saved in this browser per symbol and timeframe; horizontal lines show on every timeframe. Scroll or pinch to zoom, drag to pan — older candles load as
        you reach the left edge. {isStock ? "Stock volume is shares" : "Index volume is turnover in NPR"}
        {meta?.basis === "adjusted" ? "; prices are bonus/right-adjusted." : "."}
        {last ? ` ${formatCompact(bars.length, 1)} candles loaded.` : ""}
      </p>
    </AppShell>
  );
}
