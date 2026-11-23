import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppShell } from "../components/AppShell";
import { TopBar } from "../components/TopBar";
import { NavLinks } from "../components/NavLinks";
import { Metric, Notice } from "../components/Panel";
import { SecurityPicker } from "../components/SecurityPicker";
import { AXIS, COLORS, GRID, TOOLTIP } from "../lib/chart";
import { axisDay, formatCompact, formatDay, formatNumber, formatPct, trendColor } from "../lib/format";
import { useApi, useLogout } from "../lib/useApi";

// Calendar-day windows over the daily closes (indices: market_index_daily,
// NEPSE back to 2000; stocks: market_stock_daily, back to 2000-2010 or
// listing); 0 = full history. Indicators are computed over the full
// history server-side, so even a short window starts with a warmed-up
// SMA 200.
const WINDOW_OPTIONS = [
  { value: 90, label: "90d" },
  { value: 180, label: "180d" },
  { value: 365, label: "1y" },
  { value: 730, label: "2y" },
  { value: 1825, label: "5y" },
  { value: 3650, label: "10y" },
  { value: 0, label: "Max" },
];

const BASIS_OPTIONS = [
  { value: "adjusted", label: "Adjusted", title: "Bonus/right-adjusted prices: no artificial drops on ex-dates (use for indicators)" },
  { value: "raw", label: "Raw", title: "Prices as traded: drop by the bonus ratio on every ex-date" },
];

// Point dates are plain "YYYY-MM-DD" (see formatDay for why they're never
// parsed as UTC midnight).
function formatPointDate(dateString) {
  return formatDay(dateString);
}

// Trailing mean over `period` points (null until enough points).
function rollingMean(values, period) {
  const out = [];
  let sum = 0;
  let count = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i] ?? 0;
    sum += v;
    count++;
    if (count > period) {
      sum -= values[i - period] ?? 0;
      count--;
    }
    out.push(count === period ? sum / period : null);
  }
  return out;
}

export function TechnicalsPage() {
  const onLogout = useLogout();
  const [params, setParams] = useSearchParams();
  const [days, setDays] = useState(365);
  const [basis, setBasis] = useState("adjusted");

  // The selection lives in the URL (?index=NEPSE or ?stock=NABIL) so a chart
  // can be bookmarked or shared.
  const stockParam = params.get("stock");
  const selected = stockParam ? { kind: "stock", id: stockParam.toUpperCase() } : { kind: "index", id: params.get("index") || "NEPSE" };
  const isStock = selected.kind === "stock";

  const indices = useApi("/dashboard/indices");
  const indicators = useApi(
    isStock
      ? `/dashboard/stock-indicators?symbol=${encodeURIComponent(selected.id)}&days=${days}&basis=${basis}`
      : `/dashboard/indicators?index_name=${encodeURIComponent(selected.id)}&days=${days}`,
  );

  // useApi keeps the previous response while a new one loads; only show
  // data that belongs to the current selection.
  const data = indicators.data && indicators.data.index_name === selected.id ? indicators.data : null;
  const points = useMemo(() => {
    const raw = data?.points || [];
    const activity = raw.map((p) => (isStock ? p.volume : p.turnover));
    const avg = rollingMean(activity, 20);
    return raw.map((p, i) => ({ ...p, activity: activity[i], activity_avg: avg[i] }));
  }, [data, isStock]);
  const daysAvailable = data?.days_available ?? null;
  const longSpan = days === 0 || days > 400;
  const last = points[points.length - 1];
  const prev = points[points.length - 2];

  function select(kind, id) {
    setParams(kind === "stock" ? { stock: id } : { index: id });
  }

  const indexInfo = !isStock ? (indices.data?.indices || []).find((i) => i.index_name === selected.id) : null;
  const closeLabel = isStock && data?.basis === "adjusted" ? "Adjusted close" : "Close";
  const errors = [indices.error, indicators.error].filter(Boolean);

  return (
    <AppShell
      title="Technical Analysis"
      subtitle="SMA, EMA, MACD, RSI and Bollinger Bands over the daily closes of every NEPSE index and individual stock"
      actions={<TopBar onLogout={onLogout} rightLink={<NavLinks />} />}
    >
      {errors.map((e) => (
        <Notice key={e} tone="rose">
          {e.includes("stock-indicators") ? `No daily history for ${selected.id}.` : e}
        </Notice>
      ))}

      {/* Header controls. relative z-20: every .panel's backdrop-blur makes
          its own stacking context, so without it the cards below paint over
          the search dropdown. */}
      <section className="panel relative z-20 mb-4 flex flex-wrap items-end gap-3">
        <SecurityPicker indices={indices.data?.indices} selected={selected} onSelect={select} />

        <div>
          <label className="mb-1 block text-xs uppercase tracking-widest text-slate-400" htmlFor="days-select">
            Window
          </label>
          <select
            id="days-select"
            className="rounded-xl border border-slate-600 bg-slate-900/70 px-3 py-2 text-sm text-slate-100"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {WINDOW_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {isStock ? (
          <div>
            <span className="mb-1 block text-xs uppercase tracking-widest text-slate-400">Prices</span>
            <div className="flex gap-1">
              {BASIS_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  title={opt.title}
                  onClick={() => setBasis(opt.value)}
                  className={`rounded-lg border px-3 py-2 text-sm ${
                    basis === opt.value ? "border-cyan-300 bg-cyan-500/20 text-cyan-200" : "border-slate-600 bg-slate-800/80 text-slate-200"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="ml-auto text-sm text-slate-400">{indicators.loading ? "Loading…" : `${points.length} sessions shown`}</div>
      </section>

      {/* What is selected */}
      <section className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Metric
          label={isStock ? data?.symbol || selected.id : "Index"}
          value={isStock ? data?.symbol || selected.id : selected.id}
          sub={isStock ? [data?.name, data?.sector].filter(Boolean).join(" · ") || " " : `${formatNumber(indexInfo?.distinct_days ?? daysAvailable, 0)} sessions since ${indexInfo?.first_date ?? "-"}`}
        />
        <Metric
          label={isStock ? "Last close (as traded)" : "Last close"}
          value={formatNumber(isStock ? data?.close : last?.close, 2)}
          tone={trendColor(isStock ? data?.change_pct : last && prev ? last.close - prev.close : 0)}
          sub={
            isStock
              ? `${formatPct(data?.change_pct, 2, true)} on ${formatDay(data?.last_date)}`
              : last && prev
                ? `${formatPct(((last.close - prev.close) / prev.close) * 100, 2, true)} on ${formatDay(last.date)}`
                : " "
          }
        />
        {isStock ? (
          <Metric
            label="52-week range"
            value={`${formatNumber(data?.low_52w, 2)} – ${formatNumber(data?.high_52w, 2)}`}
            sub={data?.basis === "adjusted" ? "adjusted prices, last 365 days of history" : "raw prices, last 365 days of history"}
          />
        ) : (
          <Metric label="RSI 14" value={formatNumber(last?.rsi_14, 1)} sub={last?.rsi_14 >= 70 ? "overbought (≥ 70)" : last?.rsi_14 <= 30 ? "oversold (≤ 30)" : "neutral"} />
        )}
        {isStock ? (
          <Metric
            label="Status"
            value={data?.status || "-"}
            tone={data?.trading ? "text-emerald-300" : "text-amber-300"}
            sub={`${formatNumber(daysAvailable, 0)} sessions, ${data?.first_date ?? "-"} → ${data?.last_date ?? "-"}`}
          />
        ) : (
          <Metric
            label="vs SMA 200"
            value={last?.sma_200 ? formatPct(((last.close - last.sma_200) / last.sma_200) * 100, 1, true) : "-"}
            tone={last?.sma_200 ? trendColor(last.close - last.sma_200) : "text-slate-100"}
            sub="close relative to its 200-session average"
          />
        )}
      </section>

      {isStock && data && !data.trading ? (
        <Notice>
          {data.symbol} {data.status ? `is ${data.status.toLowerCase()}` : "no longer trades"} — its history ends on {formatDay(data.last_date)}, so the window is
          counted back from that date.
        </Notice>
      ) : null}
      {isStock && data && basis === "adjusted" && data.basis === "raw" ? (
        <Notice>
          merolagani has no bonus/right-adjusted history for {data.symbol}, so these are raw prices — they drop on every bonus/right ex-date, which moving averages and RSI read as
          a fall.
        </Notice>
      ) : null}
      {!indicators.loading && daysAvailable !== null && daysAvailable < 200 ? (
        <Notice>
          Only {daysAvailable} sessions of history for {selected.id} — the 200-session moving average needs 200.
        </Notice>
      ) : null}

      {/* Price + Moving Averages */}
      <section className="panel mb-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-display text-xl font-semibold">Price &amp; Moving Averages</h3>
          <span className="text-xs text-slate-400">
            {isStock ? `${closeLabel.toLowerCase()} · ` : ""}SMA 20 / 50 / 200 sessions
          </span>
        </div>
        <div className="h-96">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points}>
              <defs>
                <linearGradient id="closeFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={(v) => axisDay(v, longSpan)} minTickGap={36} stroke={AXIS} />
              <YAxis domain={["auto", "auto"]} stroke={AXIS} />
              <Tooltip {...TOOLTIP} labelFormatter={(v) => formatPointDate(v)} formatter={(v, name) => [formatNumber(v, 2), name]} />
              <Legend />
              <Area type="monotone" dataKey="close" name={closeLabel} stroke="#2dd4bf" fill="url(#closeFill)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma_20" name="SMA 20" stroke="#fbbf24" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma_50" name="SMA 50" stroke="#60a5fa" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma_200" name="SMA 200" stroke="#c4b5fd" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Volume / turnover */}
      <section className="panel mb-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-display text-xl font-semibold">{isStock ? "Volume" : "Turnover"}</h3>
          <span className="text-xs text-slate-400">{isStock ? "shares traded per session" : "NPR traded per session"} · line = 20-session average</span>
        </div>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={(v) => axisDay(v, longSpan)} minTickGap={36} stroke={AXIS} />
              <YAxis stroke={AXIS} tickFormatter={(v) => formatCompact(v, 1)} width={56} />
              <Tooltip {...TOOLTIP} labelFormatter={(v) => formatPointDate(v)} formatter={(v, name) => [formatCompact(v, 2), name]} />
              <Bar dataKey="activity" name={isStock ? "Volume" : "Turnover"} fill={COLORS.slate} isAnimationActive={false} />
              <Line type="monotone" dataKey="activity_avg" name="20-session avg" stroke={COLORS.amber} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Bollinger Bands */}
      <section className="panel mb-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-display text-xl font-semibold">Bollinger Bands</h3>
          <span className="text-xs text-slate-400">20-period, upper / middle / lower</span>
        </div>
        <div className="h-96">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={(v) => axisDay(v, longSpan)} minTickGap={36} stroke={AXIS} />
              <YAxis domain={["auto", "auto"]} stroke={AXIS} />
              <Tooltip {...TOOLTIP} labelFormatter={(v) => formatPointDate(v)} formatter={(v, name) => [formatNumber(v, 2), name]} />
              <Legend />
              {/* Band fill: Recharts has no first-class "area between two lines" mark,
                  and stacking two Areas to fake one (upper fill, then lower painted
                  over in the background color) breaks as soon as the Y axis
                  autoscales per panel or the panel isn't opaque, producing a
                  misleading shape. Three plain Lines (dashed upper/lower, solid
                  middle) is the simpler, honest rendering used here instead. */}
              <Line type="monotone" dataKey="close" name={closeLabel} stroke="#2dd4bf" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="bollinger_upper" name="Upper" stroke="#818cf8" strokeWidth={1.25} strokeDasharray="4 3" dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="bollinger_middle" name="Middle (SMA 20)" stroke="#fbbf24" strokeWidth={1.25} dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="bollinger_lower" name="Lower" stroke="#818cf8" strokeWidth={1.25} strokeDasharray="4 3" dot={false} connectNulls={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* MACD */}
      <section className="panel mb-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-display text-xl font-semibold">MACD</h3>
          <span className="text-xs text-slate-400">12/26 EMA convergence-divergence, 9-period signal</span>
        </div>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={(v) => axisDay(v, longSpan)} minTickGap={36} stroke={AXIS} />
              <YAxis domain={["auto", "auto"]} stroke={AXIS} />
              <Tooltip {...TOOLTIP} labelFormatter={(v) => formatPointDate(v)} formatter={(v, name) => [formatNumber(v, 3), name]} />
              <Legend />
              <Bar dataKey="macd_histogram" name="Histogram" fill="#94a3b8" isAnimationActive={false}>
                {points.map((p, idx) => (
                  <Cell key={idx} fill={Number(p.macd_histogram) >= 0 ? "#34d399" : "#f87171"} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="macd" name="MACD" stroke="#60a5fa" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="macd_signal" name="Signal" stroke="#fbbf24" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* RSI */}
      <section className="panel">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-display text-xl font-semibold">RSI (14)</h3>
          <span className="text-xs text-slate-400">relative strength index</span>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={(v) => axisDay(v, longSpan)} minTickGap={36} stroke={AXIS} />
              <YAxis domain={[0, 100]} stroke={AXIS} />
              <Tooltip {...TOOLTIP} labelFormatter={(v) => formatPointDate(v)} formatter={(v, name) => [formatNumber(v, 2), name]} />
              <ReferenceLine y={70} stroke="#f87171" strokeDasharray="4 3" label={{ value: "Overbought", position: "insideTopRight", fill: "#f87171", fontSize: 11 }} />
              <ReferenceLine y={30} stroke="#34d399" strokeDasharray="4 3" label={{ value: "Oversold", position: "insideBottomRight", fill: "#34d399", fontSize: 11 }} />
              <Line type="monotone" dataKey="rsi_14" name="RSI 14" stroke="#c4b5fd" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </AppShell>
  );
}
