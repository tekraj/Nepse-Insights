import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS, GRID, TOOLTIP } from "../../lib/chart";
import { axisDay, formatCompact, formatNumber } from "../../lib/format";
import { DIVERGING, SERIES, STATUS, num, rows } from "../../lib/bi";
import { EmptyChart } from "../Panel";

// Charts for the BI and Portfolio pages. One y-axis per chart (never dual),
// 1.5-2px lines, a legend from two series up, tooltips on every chart.
// Series colours come from the validated SERIES order; up/down candles use
// the reserved status colours.

const SLATE = "#94a3b8";
const SYNC = "bi-price";
const axisProps = { stroke: AXIS, tick: { fill: AXIS, fontSize: 11 }, tickLine: false };
const legendProps = { wrapperStyle: { fontSize: 12, color: "#cbd5e1" }, iconType: "plainline" as const };

function dateTicks(longSpan) {
  return (d) => axisDay(d, longSpan);
}

// Overlay lines in a fixed order; past the sixth coloured series the rest
// fold to neutral slate (still named in the legend and tooltip).
function overlayStyles(keys: string[]) {
  const order = (k) => (k.startsWith("sma_") ? 0 : k.startsWith("ema_") ? 1 : k === "vwap" ? 2 : k.startsWith("ichimoku") ? 3 : 4);
  const sorted = [...keys].filter((k) => !k.startsWith("bb_") && k !== "volume_ma").sort((a, b) => order(a) - order(b) || a.localeCompare(b, undefined, { numeric: true }));
  const out = {};
  sorted.forEach((k, i) => {
    out[k] = { color: i < SERIES.length ? SERIES[i] : SLATE, dash: k.startsWith("ema_") ? "5 3" : k.startsWith("ichimoku_span") ? "2 3" : undefined };
  });
  return out;
}

function label(key: string) {
  if (key.startsWith("sma_")) return `SMA ${key.slice(4)}`;
  if (key.startsWith("ema_")) return `EMA ${key.slice(4)}`;
  if (key === "vwap") return "VWAP";
  if (key.startsWith("ichimoku_")) return `Ichimoku ${key.slice(9).replace("_", " ")}`;
  return key;
}

// Candle: the Bar spans [low, high]; draw the wick over it and the open/close body.
function Candle(props) {
  const { x, y, width, height, payload } = props;
  if (!payload || payload.low == null || payload.high == null) return null;
  const { open, close, low, high } = payload;
  const span = high - low || 1;
  const px = (v) => y + height - ((v - low) / span) * height;
  const up = close >= open;
  const color = up ? STATUS.good : STATUS.critical;
  const top = px(Math.max(open, close));
  const bodyH = Math.max(1, Math.abs(px(open) - px(close)));
  const cx = x + width / 2;
  const w = Math.max(1, width * 0.7);
  return (
    <g>
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - w / 2} y={top} width={w} height={bodyH} fill={color} rx={1} />
    </g>
  );
}

function PriceTooltip({ active = false, payload = [], label: d = "" }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div style={TOOLTIP.contentStyle} className="px-3 py-2 text-xs">
      <p className="mb-1 text-slate-200">{d}</p>
      {p.open != null ? (
        <p className="text-slate-300">
          O {num(p.open)} · H {num(p.high)} · L {num(p.low)} · C <span className="text-slate-100">{num(p.close)}</span>
        </p>
      ) : (
        <p className="text-slate-300">Close <span className="text-slate-100">{num(p.close)}</span></p>
      )}
      {payload
        .filter((it) => it.dataKey !== "hl" && it.dataKey !== "close" && it.value != null)
        .map((it) => (
          <p key={it.dataKey} className="text-slate-400">
            <span style={{ color: it.color }}>━</span> {it.name}: {num(it.value)}
          </p>
        ))}
    </div>
  );
}

export function PriceChart({ tech, height = 360 }) {
  const c = tech?.charts;
  if (!c?.dates?.length) return <EmptyChart label="No price data" />;
  const candles = c.candles;
  const overlays = c.overlays || {};
  const styles = overlayStyles(Object.keys(overlays));
  const data = rows(c.dates, {
    close: c.close,
    ...(candles ? { open: candles.open, high: candles.high, low: candles.low } : {}),
    ...Object.fromEntries(Object.entries(overlays).filter(([k]) => k !== "volume_ma")),
  }).map((r) => (candles ? { ...r, hl: [r.low, r.high] } : r));
  const longSpan = c.dates.length > 300;
  const bb = overlays.bb_upper ? ["bb_upper", "bb_middle", "bb_lower"] : [];
  const lines = c.lines || [];
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} syncId={SYNC} margin={{ top: 8, right: 64, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" {...axisProps} tickFormatter={dateTicks(longSpan)} minTickGap={40} />
          <YAxis {...axisProps} domain={["auto", "auto"]} width={60} tickFormatter={(v) => formatNumber(v, 0)} />
          <Tooltip content={<PriceTooltip />} />
          <Legend {...legendProps} />
          {candles ? (
            <Bar dataKey="hl" name="Price (OHLC)" shape={<Candle />} isAnimationActive={false} legendType="none" />
          ) : (
            <Line dataKey="close" name="Close" stroke="#e2e8f0" strokeWidth={1.8} dot={false} isAnimationActive={false} />
          )}
          {bb.map((k) => (
            <Line key={k} dataKey={k} name={k === "bb_middle" ? "Bollinger mid" : k === "bb_upper" ? "Bollinger upper" : "Bollinger lower"}
              stroke={SLATE} strokeWidth={1} strokeDasharray={k === "bb_middle" ? "4 3" : undefined} dot={false} isAnimationActive={false} />
          ))}
          {Object.keys(styles).map((k) => (
            <Line key={k} dataKey={k} name={label(k)} stroke={styles[k].color} strokeDasharray={styles[k].dash} strokeWidth={1.5}
              dot={false} isAnimationActive={false} connectNulls />
          ))}
          {lines.map((l, i) => (
            <ReferenceLine key={`${l.kind}-${i}`} y={l.price} stroke={l.kind === "fibonacci" ? SERIES[5] : SLATE}
              strokeDasharray={l.kind === "resistance" ? "6 3" : l.kind === "support" ? "2 3" : "1 4"} strokeOpacity={0.8}
              label={{ value: `${l.kind === "fibonacci" ? l.label : `${l.kind === "support" ? "S" : "R"} ${num(l.price, 1)}`}`, position: "right", fill: "#cbd5e1", fontSize: 10 }} />
          ))}
          {(c.markers || []).filter((m) => data.some((r) => r.date === m.date)).map((m, i) => {
            const r = data.find((row) => row.date === m.date);
            return (
              <ReferenceDot key={i} x={m.date} y={m.direction === "bearish" ? (r.high ?? r.close) : (r.low ?? r.close)} r={5}
                fill={m.direction === "bullish" ? STATUS.good : m.direction === "bearish" ? STATUS.critical : SLATE}
                stroke="#0f172a" strokeWidth={2} />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function VolumeChart({ tech, height = 120 }) {
  const c = tech?.charts;
  if (!c?.volume) return null;
  const data = rows(c.dates, { volume: c.volume, avg: c.overlays?.volume_ma, close: c.close });
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} syncId={SYNC} margin={{ top: 4, right: 64, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis {...axisProps} width={60} tickFormatter={(v) => formatCompact(v, 1)} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [formatCompact(v, 2), n]} />
          <Legend {...legendProps} />
          <Bar dataKey="volume" name="Volume" isAnimationActive={false} radius={[2, 2, 0, 0]}>
            {data.map((r, i) => (
              <Cell key={i} fill={i > 0 && r.close < data[i - 1].close ? STATUS.critical : STATUS.good} fillOpacity={0.55} />
            ))}
          </Bar>
          {c.overlays?.volume_ma ? <Line dataKey="avg" name="Average" stroke={SERIES[0]} strokeWidth={1.5} dot={false} isAnimationActive={false} /> : null}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

const PANEL_TITLES = {
  rsi: "RSI", macd: "MACD", stochastic: "Stochastic", adx: "ADX / DMI", atr: "ATR", obv: "On-Balance Volume",
  mfi: "Money Flow Index", cci: "CCI", williams_r: "Williams %R",
};

export function IndicatorPanel({ tech, name, height = 150 }) {
  const c = tech?.charts;
  const p = c?.panels?.[name];
  if (!p) return null;
  let series = [];
  let refs = [];
  let histogram = null;
  if (name === "rsi") {
    series = [{ key: "values", label: `RSI ${p.period}` }];
    refs = [p.overbought, 50, p.oversold];
  } else if (name === "macd") {
    series = [{ key: "macd", label: "MACD" }, { key: "signal", label: "Signal" }];
    histogram = "histogram";
    refs = [0];
  } else if (name === "stochastic") {
    series = [{ key: "k", label: "%K" }, { key: "d", label: "%D" }];
    refs = [80, 20];
  } else if (name === "adx") {
    series = [{ key: "adx", label: "ADX" }, { key: "plus_di", label: "+DI" }, { key: "minus_di", label: "-DI" }];
    refs = [25];
  } else {
    series = [{ key: "values", label: PANEL_TITLES[name] }];
    refs = name === "mfi" ? [80, 20] : name === "cci" ? [100, -100] : name === "williams_r" ? [-20, -80] : [];
  }
  const cols = Object.fromEntries(Object.keys(p).filter((k) => Array.isArray(p[k])).map((k) => [k, p[k]]));
  const data = rows(c.dates, cols);
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} syncId={SYNC} margin={{ top: 4, right: 64, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis {...axisProps} width={60} domain={["auto", "auto"]} tickFormatter={(v) => formatNumber(v, 1)} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [num(v), n]} />
          {series.length > 1 || histogram ? <Legend {...legendProps} /> : null}
          {refs.map((r) => <ReferenceLine key={r} y={r} stroke={SLATE} strokeDasharray="3 3" strokeOpacity={0.6} />)}
          {histogram ? (
            <Bar dataKey={histogram} name="Histogram" isAnimationActive={false}>
              {data.map((r, i) => <Cell key={i} fill={(r[histogram] ?? 0) >= 0 ? DIVERGING.positive : DIVERGING.negative} fillOpacity={0.6} />)}
            </Bar>
          ) : null}
          {series.map((s, i) => (
            <Line key={s.key} dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export { PANEL_TITLES };

export function IntradayChart({ tech, height = 200 }) {
  const day = tech?.charts?.intraday;
  if (!day?.points?.length) return <EmptyChart label="No live-session data" />;
  const data = day.points.map((p) => ({ t: String(p.time).slice(11, 16), price: p.price }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="t" {...axisProps} minTickGap={30} />
          <YAxis {...axisProps} domain={["auto", "auto"]} width={60} />
          <Tooltip {...TOOLTIP} formatter={(v) => [num(v), "Last price"]} />
          <Line dataKey="price" name="Last price" stroke={SERIES[0]} strokeWidth={1.8} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------- generic small charts

export function SeriesLine({ dates, values, name, color = SERIES[0], height = 180, unit = "", area = false, refY = null }) {
  if (!dates?.length) return <EmptyChart label="No data" />;
  const data = rows(dates, { v: values });
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" {...axisProps} tickFormatter={dateTicks(dates.length > 300)} minTickGap={40} />
          <YAxis {...axisProps} width={52} domain={["auto", "auto"]} tickFormatter={(v) => `${formatNumber(v, 1)}${unit}`} />
          <Tooltip {...TOOLTIP} formatter={(v) => [`${num(v)}${unit}`, name]} />
          {refY !== null ? <ReferenceLine y={refY} stroke={SLATE} strokeDasharray="3 3" /> : null}
          {area ? (
            <Area dataKey="v" name={name} stroke={color} fill={color} fillOpacity={0.18} strokeWidth={1.5} isAnimationActive={false} />
          ) : (
            <Line dataKey="v" name={name} stroke={color} strokeWidth={1.8} dot={false} isAnimationActive={false} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// Grouped bars: rows [{label, a, b, ...}], series [{key, name}].
export function GroupedBars({ data, xKey, series, height = 220, unit = "", layout = "horizontal" }) {
  if (!data?.length) return <EmptyChart label="No data" />;
  const vertical = layout === "vertical";
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} layout={vertical ? "vertical" : "horizontal"} margin={{ top: 8, right: 16, bottom: 0, left: vertical ? 8 : 0 }}
          barGap={2} barCategoryGap="22%">
          <CartesianGrid stroke={GRID} vertical={vertical} horizontal={!vertical} />
          {vertical ? (
            <>
              <XAxis type="number" {...axisProps} tickFormatter={(v) => `${formatNumber(v, 1)}${unit}`} />
              <YAxis type="category" dataKey={xKey} {...axisProps} width={120} interval={0} />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} {...axisProps} />
              <YAxis {...axisProps} width={52} tickFormatter={(v) => `${formatNumber(v, 1)}${unit}`} />
            </>
          )}
          <Tooltip {...TOOLTIP} formatter={(v, n) => [`${num(v)}${unit}`, n]} cursor={{ fill: "rgba(148,163,184,.08)" }} />
          {series.length > 1 ? <Legend {...legendProps} iconType="square" /> : null}
          <ReferenceLine {...(vertical ? { x: 0 } : { y: 0 })} stroke={SLATE} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color || SERIES[i]} radius={vertical ? [0, 4, 4, 0] : [4, 4, 0, 0]} isAnimationActive={false}>
              {s.cellColor ? data.map((r, j) => <Cell key={j} fill={s.cellColor(r)} />) : null}
            </Bar>
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// Histogram (bars) with an optional reference curve (e.g. the normal fit).
export function Histogram({ centers, counts, curve = null, height = 200, xUnit = "%", marker = null, markerLabel = "" }) {
  if (!centers?.length) return <EmptyChart label="No data" />;
  const data = centers.map((c, i) => ({ x: Number(c).toFixed(2), count: counts[i], curve: curve ? curve[i] : null }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} barCategoryGap={1}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="x" {...axisProps} tickFormatter={(v) => `${Number(v).toFixed(1)}${xUnit}`} minTickGap={30} />
          <YAxis {...axisProps} width={44} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [num(v, 1), n]} labelFormatter={(v) => `${v}${xUnit}`} />
          {curve ? <Legend {...legendProps} /> : null}
          <Bar dataKey="count" name="Observations" fill={SERIES[0]} fillOpacity={0.7} isAnimationActive={false} radius={[2, 2, 0, 0]} />
          {curve ? <Line dataKey="curve" name="Normal fit" stroke={SERIES[1]} strokeWidth={1.5} dot={false} isAnimationActive={false} /> : null}
          {marker !== null ? (
            <ReferenceLine x={data.reduce((best, r) => (Math.abs(r.x - marker) < Math.abs(best.x - marker) ? r : best), data[0]).x}
              stroke="#e2e8f0" strokeDasharray="4 3" label={{ value: markerLabel, fill: "#e2e8f0", fontSize: 11, position: "top" }} />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// Percentile fan: p5-p95 and p25-p75 bands (one hue, two steps) + median line.
export function Fan({ xs, p, height = 220, unit = "", xLabel = (x) => x, refY = null, refLabel = "" }) {
  if (!xs?.length || !p?.p50) return <EmptyChart label="No data" />;
  const data = xs.map((x, i) => ({ x, outer: [p.p5[i], p.p95[i]], inner: [p.p25[i], p.p75[i]], median: p.p50[i] }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="x" {...axisProps} tickFormatter={xLabel} minTickGap={24} />
          <YAxis {...axisProps} width={56} domain={["auto", "auto"]} tickFormatter={(v) => `${formatNumber(v, 1)}${unit}`} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [Array.isArray(v) ? `${num(v[0])}${unit} – ${num(v[1])}${unit}` : `${num(v)}${unit}`, n]}
            labelFormatter={xLabel} />
          <Legend {...legendProps} iconType="square" />
          {refY !== null ? <ReferenceLine y={refY} stroke="#e2e8f0" strokeDasharray="4 3" label={{ value: refLabel, fill: "#e2e8f0", fontSize: 11, position: "insideTopLeft" }} /> : null}
          <Area dataKey="outer" name="90% range" stroke="none" fill="#86b6ef" fillOpacity={0.18} isAnimationActive={false} />
          <Area dataKey="inner" name="50% range" stroke="none" fill="#3987e5" fillOpacity={0.35} isAnimationActive={false} />
          <Line dataKey="median" name="Median" stroke="#cde2fb" strokeWidth={1.8} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// Efficient frontier with the chosen portfolio and the target return.
export function FrontierChart({ frontier, chosen, target, height = 240 }) {
  if (!frontier?.length) return <EmptyChart label="No frontier" />;
  const pts = frontier.map((f) => ({ x: f.volatility_pct, frontier: f.return_pct }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={pts} margin={{ top: 8, right: 24, bottom: 16, left: 0 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis dataKey="x" type="number" domain={["auto", "auto"]} {...axisProps} tickFormatter={(v) => `${formatNumber(v, 1)}%`}
            label={{ value: "Risk (volatility over the horizon)", fill: AXIS, fontSize: 11, position: "insideBottom", offset: -8 }} />
          <YAxis {...axisProps} width={52} domain={["auto", "auto"]} tickFormatter={(v) => `${formatNumber(v, 1)}%`} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [`${num(v)}%`, n]} labelFormatter={(v) => `Volatility ${num(v)}%`} />
          <Legend {...legendProps} verticalAlign="top" />
          {target !== null && target !== undefined ? (
            <ReferenceLine y={target} stroke="#e2e8f0" strokeDasharray="4 3" label={{ value: `Target ${num(target)}%`, fill: "#e2e8f0", fontSize: 11, position: "insideTopRight" }} />
          ) : null}
          <Line dataKey="frontier" name="Efficient frontier (expected return)" stroke={SERIES[0]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
          {chosen ? (
            <Scatter data={[{ x: chosen.volatility_pct, chosen: chosen.return_pct }]} dataKey="chosen" name="Your portfolio" fill={SERIES[1]}
              shape={(props) => <circle cx={props.cx} cy={props.cy} r={7} fill={SERIES[1]} stroke="#0f172a" strokeWidth={2} />} isAnimationActive={false} />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
