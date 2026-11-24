import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { NavLinks } from "../components/NavLinks";
import { Metric, Notice, Panel } from "../components/Panel";
import { TopBar } from "../components/TopBar";
import { ChatPanel } from "../components/bi/ChatPanel";
import { Fan, GroupedBars, Histogram, IndicatorPanel, IntradayChart, PANEL_TITLES, PriceChart, SeriesLine, VolumeChart } from "../components/bi/BiCharts";
import { MiniMarkdown } from "../components/bi/MiniMarkdown";
import { DIRECTION_STYLE, DIVERGING, RECOMMENDATION_ICON, RECOMMENDATION_LABEL, RECOMMENDATION_STYLE, SERIES, apiJson, num, signedPct } from "../lib/bi";
import { formatCompact, shortDateTime, timeAgo } from "../lib/format";
import { useApi, useLogout } from "../lib/useApi";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "technical", label: "Technical" },
  { id: "fundamental", label: "Fundamental" },
  { id: "news", label: "News" },
  { id: "quant", label: "Quant" },
];

export function RecommendationBadge({ rec, large = false }) {
  if (!rec) return <span className="text-sm text-slate-400">no report</span>;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 ${large ? "py-1.5 text-base" : "py-0.5 text-xs"} font-semibold ${RECOMMENDATION_STYLE[rec] || ""}`}>
      <span aria-hidden="true">{RECOMMENDATION_ICON[rec]}</span>
      {RECOMMENDATION_LABEL[rec] || rec}
    </span>
  );
}

// -100..100 score as a bar from the centre (polarity: diverging colours,
// plus the signed number, so it never relies on colour alone).
function ScoreBar({ score }) {
  if (score === null || score === undefined) return <span className="text-slate-400">-</span>;
  const s = Math.max(-100, Math.min(100, Number(score)));
  const width = Math.abs(s) / 2;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-32 rounded-full bg-slate-800">
        <div className="absolute top-0 h-2 w-px bg-slate-500" style={{ left: "50%" }} />
        <div className="absolute top-0 h-2 rounded-full" style={{ left: s >= 0 ? "50%" : `${50 - width}%`, width: `${width}%`, background: s >= 0 ? DIVERGING.positive : DIVERGING.negative }} />
      </div>
      <span className="font-mono text-sm text-slate-200">{s > 0 ? "+" : ""}{s.toFixed(0)}</span>
    </div>
  );
}

function SignalList({ signals }) {
  if (!signals?.length) return <p className="text-sm text-slate-400">No signals.</p>;
  const sorted = [...signals].sort((a, b) => b.strength * (b.weight || 1) - a.strength * (a.weight || 1));
  return (
    <ul className="space-y-1.5">
      {sorted.map((s) => {
        const d = DIRECTION_STYLE[s.direction] || DIRECTION_STYLE.neutral;
        return (
          <li key={s.id} className="flex items-start gap-2 text-sm">
            <span className={`mt-0.5 w-4 shrink-0 text-center ${d.cls}`} aria-label={s.direction}>{d.icon}</span>
            <span className="flex-1 text-slate-200">
              {s.label}
              {s.detail ? <span className="text-slate-400"> · {s.detail}</span> : null}
            </span>
            <span className="w-20 shrink-0 text-right text-xs text-slate-400" title="signal strength">
              <span className="inline-block h-1.5 rounded bg-slate-500 align-middle" style={{ width: `${Math.round(s.strength * 48)}px` }} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function List({ title, items, tone = "text-slate-300", icon = "•" }) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-400">{title}</p>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className={`flex gap-2 text-sm ${tone}`}>
            <span aria-hidden="true">{icon}</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SectionStatus({ section }) {
  if (!section) return <Notice tone="slate">This analysis is turned off for the script (BI Setup).</Notice>;
  if (section.status === "failed") return <Notice tone="rose">Analysis failed: {section.error}</Notice>;
  if (section.status === "no_data") return <Notice tone="amber">{section.summary}</Notice>;
  return null;
}

function Overview({ report }) {
  const syn = report.synthesis || {};
  const sections = report.sections || {};
  const levels = syn.key_levels || {};
  return (
    <div className="grid gap-4">
      <Panel title="Summary" note={report.llm_used ? `Written by ${report.llm_model || "the LLM"} from the four agents' findings` : "Rule-based summary (no LLM configured)"}>
        <MiniMarkdown text={syn.summary} />
        {syn.buy_sell_view ? (
          <div className="mt-3 rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-3">
            <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-cyan-300">Buy / sell view</p>
            <MiniMarkdown text={syn.buy_sell_view} />
          </div>
        ) : null}
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Bullish vs. bearish">
          <div className="grid gap-4 sm:grid-cols-2">
            <List title="Bullish factors" items={syn.bullish_factors} tone="text-emerald-200" icon="▲" />
            <List title="Bearish factors" items={syn.bearish_factors} tone="text-rose-200" icon="▼" />
          </div>
          <div className="mt-4">
            <List title="Risks" items={syn.risks} tone="text-amber-100" icon="⚠" />
          </div>
        </Panel>
        <Panel title="Key levels & plan">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <p className="text-slate-400">Support</p>
            <p className="text-slate-100">{(levels.support || []).map((v) => num(v)).join(" · ") || "-"}</p>
            <p className="text-slate-400">Resistance</p>
            <p className="text-slate-100">{(levels.resistance || []).map((v) => num(v)).join(" · ") || "-"}</p>
            <p className="text-slate-400">Stop loss</p>
            <p className="text-slate-100">{levels.stop_loss ? num(levels.stop_loss) : "-"}</p>
            <p className="text-slate-400">Target</p>
            <p className="text-slate-100">{levels.target ? num(levels.target) : "-"}</p>
          </div>
          {syn.action_plan ? (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-400">Action plan</p>
              <MiniMarkdown text={syn.action_plan} />
            </div>
          ) : null}
        </Panel>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {["technical", "fundamental", "news", "quant"].map((k) => {
          const s = sections[k];
          const view = syn[`${k}_view`];
          return (
            <Panel key={k} title={`${k[0].toUpperCase()}${k.slice(1)} agent`} right={s ? <ScoreBar score={s.score} /> : <span className="text-xs text-slate-500">off</span>}>
              <MiniMarkdown text={view || s?.summary || "Not run for this script."} />
            </Panel>
          );
        })}
      </div>
    </div>
  );
}

function Technical({ section }) {
  const m = section?.metrics || {};
  const panels = Object.keys(section?.charts?.panels || {});
  return (
    <div className="grid gap-4">
      <SectionStatus section={section} />
      {section?.status === "ok" ? (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Last price" value={num(m.last_close)} sub={`${signedPct(m.change_pct)} ${m.provisional_today ? "(live)" : ""}`} />
            <Metric label="52-week range" value={`${num(m.position_52w_pct, 0)}%`} sub={`${num(m.low_52w)} – ${num(m.high_52w)}`} />
            <Metric label="1M / 3M" value={signedPct(m.return_1m_pct, 1)} sub={`3M ${signedPct(m.return_3m_pct, 1)}`} />
            <Metric label="Agent score" value={<ScoreBar score={section.score} />} sub={`${section.signals.length} signals`} />
          </section>
          <Panel title="Price" note={`${section.charts.basis === "adjusted" ? "Bonus/right-adjusted" : "Raw"} daily bars; support (dotted) / resistance (dashed) zones and recent candlestick patterns`}>
            <PriceChart tech={section} />
            <VolumeChart tech={section} />
          </Panel>
          {panels.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {panels.map((p) => (
                <Panel key={p} title={PANEL_TITLES[p] || p}>
                  <IndicatorPanel tech={section} name={p} />
                </Panel>
              ))}
            </div>
          ) : null}
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Signals">
              <SignalList signals={section.signals} />
            </Panel>
            {section.charts.intraday !== undefined ? (
              <Panel title="Session price path" note={section.charts.intraday?.trade_date ? `Minute scrapes, ${section.charts.intraday.trade_date}` : "Live session"}>
                <IntradayChart tech={section} />
              </Panel>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

function Fundamental({ section }) {
  const m = section?.metrics || {};
  const c = section?.charts || {};
  const peers = (c.peer_valuation || []).filter((p) => p.pe_ratio).sort((a, b) => a.pe_ratio - b.pe_ratio);
  const brokers = (c.broker_net || []).map((b) => ({ name: `#${b.broker_code}${b.broker_name ? ` ${b.broker_name.split(" ").slice(0, 2).join(" ")}` : ""}`, net: b.net }));
  return (
    <div className="grid gap-4">
      <SectionStatus section={section} />
      {section?.status === "ok" ? (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="P/E" value={num(m.pe_ratio, 1)} sub={m.sector_median_pe ? `sector median ${num(m.sector_median_pe, 1)}` : m.eps_period} />
            <Metric label="P/BV" value={num(m.pbv, 2)} sub={m.sector_median_pbv ? `sector median ${num(m.sector_median_pbv, 2)}` : `BV ${num(m.book_value)}`} />
            <Metric label="EPS" value={num(m.eps)} sub={m.eps_period} />
            <Metric label="Dividend yield" value={m.dividend_yield_pct != null ? `${num(m.dividend_yield_pct, 1)}%` : "-"} sub={m.cash_dividend_pct != null ? `${num(m.cash_dividend_pct)}% cash, ${num(m.bonus_pct)}% bonus` : null} />
            <Metric label="Graham value" value={num(m.graham_value)} sub={m.graham_margin_pct != null ? `${signedPct(m.graham_margin_pct, 0)} vs. price` : null} />
            <Metric label="Market cap" value={m.market_cap ? `NPR ${formatCompact(m.market_cap)}` : "-"} sub={m.shares_outstanding ? `${formatCompact(m.shares_outstanding)} shares` : null} />
            <Metric label="Avg turnover" value={m.avg_turnover ? `NPR ${formatCompact(m.avg_turnover)}` : "-"} sub={m.turnover_trend_pct != null ? `trend ${signedPct(m.turnover_trend_pct, 0)}` : null} />
            <Metric label="Top-5 buyer share" value={m.top5_buy_concentration_pct != null ? `${num(m.top5_buy_concentration_pct, 0)}%` : "-"} sub={m.top5_sell_concentration_pct != null ? `sellers ${num(m.top5_sell_concentration_pct, 0)}% (${m.broker_days}d)` : null} />
          </section>
          <div className="grid gap-4 lg:grid-cols-2">
            {c.relative_performance ? (
              <Panel title="Returns vs. sector and NEPSE" note="Adjusted price returns">
                <GroupedBars data={c.relative_performance} xKey="period" unit="%"
                  series={[{ key: "stock", name: "This script" }, { key: "sector", name: "Sector median" }, { key: "nepse", name: "NEPSE" }]} />
              </Panel>
            ) : null}
            {c.dividend_history?.length ? (
              <Panel title="Dividend & bonus history" note="% of paid-up value per Nepali fiscal year">
                <GroupedBars data={c.dividend_history} xKey="fiscal_year" unit="%" series={[{ key: "cash_dividend", name: "Cash dividend" }, { key: "bonus", name: "Bonus shares" }]} />
              </Panel>
            ) : null}
            {peers.length ? (
              <Panel title="P/E vs. sector peers" note="Largest peers by market cap; this script highlighted">
                <GroupedBars data={peers} xKey="symbol" layout="vertical" height={Math.max(200, peers.length * 28 + 40)}
                  series={[{ key: "pe_ratio", name: "P/E", cellColor: (r) => (r.self ? SERIES[1] : SERIES[0]) }]} />
              </Panel>
            ) : null}
            {brokers.length ? (
              <Panel title="Broker net buying" note={`Net shares bought (sold) over ${m.broker_days} days, floor sheet`}>
                <GroupedBars data={brokers} xKey="name" layout="vertical" height={Math.max(220, brokers.length * 26 + 40)}
                  series={[{ key: "net", name: "Net shares", cellColor: (r) => (r.net >= 0 ? DIVERGING.positive : DIVERGING.negative) }]} />
              </Panel>
            ) : null}
            {c.valuation_history?.length > 5 ? (
              <Panel title="P/E history" note="Daily, from the fundamentals capture">
                <SeriesLine dates={c.valuation_history.map((h) => h.date)} values={c.valuation_history.map((h) => h.pe_ratio)} name="P/E" />
              </Panel>
            ) : null}
          </div>
          <Panel title="Signals">
            <SignalList signals={section.signals} />
          </Panel>
        </>
      ) : null}
    </div>
  );
}

function News({ section }) {
  const m = section?.metrics || {};
  const d = section?.data || {};
  const chip = (s) => (s > 0.15 ? "border-emerald-500/40 text-emerald-200" : s < -0.15 ? "border-rose-500/40 text-rose-200" : "border-slate-600 text-slate-300");
  const Article = ({ a }) => (
    <li className="rounded-xl border border-slate-700/70 bg-slate-900/50 p-3">
      <div className="flex items-start justify-between gap-2">
        <a href={a.url} target="_blank" rel="noreferrer noopener" className="text-sm font-medium text-slate-100 hover:text-cyan-200">{a.title || a.url}</a>
        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${chip(a.sentiment)}`}>
          {a.sentiment > 0.15 ? "▲" : a.sentiment < -0.15 ? "▼" : "●"} {num(a.sentiment, 2)}
        </span>
      </div>
      {a.summary ? <p className="mt-1 text-xs text-slate-300">{a.summary}</p> : a.snippet ? <p className="mt-1 line-clamp-2 text-xs text-slate-400">{a.snippet}</p> : null}
      <p className="mt-1 text-[11px] text-slate-500">{a.source} · {timeAgo(a.published_at)}{a.impact ? ` · ${a.impact} impact` : ""}</p>
    </li>
  );
  return (
    <div className="grid gap-4">
      <SectionStatus section={section} />
      {section && section.status !== "failed" ? (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Company sentiment" value={num(m.company_sentiment, 2)} sub={`${m.article_count || 0} articles`} />
            <Metric label="Market sentiment" value={num(m.market_sentiment, 2)} sub={`${m.market_article_count || 0} articles`} />
            <Metric label="Agent score" value={<ScoreBar score={section.score} />} />
            <Metric label="Rated by" value={m.llm_rated ? "LLM" : "Lexicon"} sub={(m.search_terms || []).join(", ")} />
          </section>
          <Panel title="What the news says">
            <MiniMarkdown text={section.summary} />
            <div className="mt-3 grid gap-4 md:grid-cols-3">
              <List title="Key events" items={d.key_events} />
              <List title="Catalysts" items={d.catalysts} tone="text-emerald-200" icon="▲" />
              <List title="Risks" items={d.risks} tone="text-amber-100" icon="⚠" />
            </div>
            {d.market_summary ? <p className="mt-3 text-sm text-slate-300"><span className="text-slate-400">Market: </span>{d.market_summary}</p> : null}
          </Panel>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Company news">
              <ul className="space-y-2">{(d.articles || []).map((a) => <Article key={a.id} a={a} />)}</ul>
              {!d.articles?.length ? <p className="text-sm text-slate-400">No recent articles.</p> : null}
            </Panel>
            <Panel title="Market-wide news">
              <ul className="space-y-2">{(d.market_articles || []).map((a) => <Article key={a.id} a={a} />)}</ul>
              {!d.market_articles?.length ? <p className="text-sm text-slate-400">Not enabled or none recent.</p> : null}
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Quant({ section }) {
  const m = section?.metrics || {};
  const c = section?.charts || {};
  const rs = m.return_stats || {};
  const vol = m.volatility || {};
  const v = m.var || {};
  const b = m.beta || {};
  const dd = m.drawdown || {};
  const mc = c.monte_carlo;
  return (
    <div className="grid gap-4">
      <SectionStatus section={section} />
      {section?.status === "ok" ? (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Volatility (annual)" value={vol.rolling_pct != null ? `${num(vol.rolling_pct, 1)}%` : "-"} sub={`risk: ${m.risk_level || "-"}`} />
            <Metric label="GARCH forecast" value={vol.garch ? `${num(vol.garch.forecast_volatility_pct, 1)}%` : "-"} sub={vol.garch ? `long-run ${num(vol.garch.long_run_volatility_pct, 1)}%` : null} />
            <Metric label="Sharpe / Sortino" value={num(rs.sharpe, 2)} sub={`Sortino ${num(rs.sortino, 2)}`} />
            <Metric label="Annual return" value={rs.annual_return_pct != null ? signedPct(rs.annual_return_pct, 1) : "-"} sub={`skew ${num(rs.skewness, 2)}, kurt ${num(rs.excess_kurtosis, 1)}`} />
            <Metric label="Drawdown" value={dd.current_drawdown_pct != null ? `${num(dd.current_drawdown_pct, 1)}%` : "-"} sub={dd.max_drawdown_pct != null ? `max ${num(dd.max_drawdown_pct, 1)}%` : null} />
            <Metric label={`VaR ${v.confidence ? Math.round(v.confidence * 100) : 95}%`} value={v.historical_var_pct != null ? `${num(v.historical_var_pct, 2)}%` : "-"} sub={v.historical_cvar_pct != null ? `CVaR ${num(v.historical_cvar_pct, 2)}% · ${v.horizon_days} session(s)` : null} />
            <Metric label="Beta vs. NEPSE" value={num(b.beta, 2)} sub={b.alpha_annual_pct != null ? `alpha ${signedPct(b.alpha_annual_pct, 1)}/yr, R² ${num(b.r_squared, 2)}` : null} />
            <Metric label="Jumps (1y)" value={m.jumps?.jumps_last_year ?? "-"} sub={m.jumps ? `${m.jumps.down_jumps_last_year} down · ${num(m.jumps.jump_variation_share_pct, 0)}% of variation` : null} />
          </section>
          <div className="grid gap-4 lg:grid-cols-2">
            {c.drawdown ? (
              <Panel title="Drawdown from peak" note="% below the running maximum (adjusted)">
                <SeriesLine dates={c.drawdown.dates} values={c.drawdown.values} name="Drawdown" unit="%" area color={SERIES[0]} refY={0} />
              </Panel>
            ) : null}
            {c.rolling_volatility ? (
              <Panel title="Rolling volatility" note="Annualised, rolling window">
                <SeriesLine dates={c.rolling_volatility.dates} values={c.rolling_volatility.values} name="Volatility" unit="%" />
              </Panel>
            ) : null}
            {mc ? (
              <Panel title="Monte Carlo price range" note={`${mc.days} sessions ahead · ${num(m.monte_carlo?.probability_up_pct, 0)}% of paths end higher (historical drift, not a forecast)`}>
                <Fan xs={mc.days} p={{ p5: mc.p5, p25: mc.p25, p50: mc.p50, p75: mc.p75, p95: mc.p95 }} unit="" xLabel={(x) => `+${x}`} refY={mc.start_price} refLabel="Now" />
              </Panel>
            ) : null}
            {c.distribution ? (
              <Panel title="Daily return distribution" note="Last ~3 years vs. a normal curve with the same mean/std (fat tails show at the edges)">
                <Histogram centers={c.distribution.centers} counts={c.distribution.counts} curve={c.distribution.normal} />
              </Panel>
            ) : null}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Signals">
              <SignalList signals={section.signals} />
            </Panel>
            <Panel title="Model details">
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                {vol.garch ? (
                  <>
                    <span className="text-slate-400">GARCH α / β</span>
                    <span>{num(vol.garch.alpha, 3)} / {num(vol.garch.beta, 3)} (half-life {num(vol.garch.half_life_days, 0)} d)</span>
                  </>
                ) : null}
                {m.hurst ? (
                  <>
                    <span className="text-slate-400">Hurst exponent</span>
                    <span>{num(m.hurst.exponent, 2)} ({m.hurst.interpretation})</span>
                  </>
                ) : null}
                {m.regime ? (
                  <>
                    <span className="text-slate-400">Volatility regime</span>
                    <span>{m.regime.regime} ({num(m.regime.percentile, 0)}th pct.)</span>
                  </>
                ) : null}
                {v.parametric_var_pct != null ? (
                  <>
                    <span className="text-slate-400">VaR Gaussian / C-F</span>
                    <span>{num(v.parametric_var_pct, 2)}% / {num(v.cornish_fisher_var_pct, 2)}%</span>
                  </>
                ) : null}
                <span className="text-slate-400">Observations</span>
                <span>{m.observations} daily returns ({m.basis})</span>
              </div>
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function BiPage() {
  const onLogout = useLogout();
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState("overview");
  const [refreshNote, setRefreshNote] = useState("");
  const [tick, setTick] = useState(0);
  const list = useApi(`/bi/reports?t=${tick}`, 60000);
  const reports = list.data?.reports || [];
  const symbol = (params.get("symbol") || reports[0]?.symbol || "").toUpperCase();
  const detail = useApi(symbol ? `/bi/reports/${encodeURIComponent(symbol)}?t=${tick}` : null, 60000);
  const report = detail.data?.summary?.symbol === symbol ? detail.data?.report : null;
  const summary = reports.find((r) => r.symbol === symbol);

  // After "Regenerate", poll until the report's generated_at changes.
  const [waitingFor, setWaitingFor] = useState(null);
  useEffect(() => {
    if (!waitingFor) return undefined;
    const started = Date.now();
    const id = window.setInterval(() => {
      setTick((t) => t + 1);
      if (Date.now() - started > 180000) setWaitingFor(null);
    }, 5000);
    return () => window.clearInterval(id);
  }, [waitingFor]);
  useEffect(() => {
    if (waitingFor && report?.generated_at && report.generated_at !== waitingFor.generated_at) {
      setWaitingFor(null);
      setRefreshNote("Report updated.");
    }
  }, [report, waitingFor]);

  async function regenerate() {
    try {
      const r = await apiJson(`/bi/reports/${encodeURIComponent(symbol)}/refresh`, "POST");
      setRefreshNote(r.message);
      setWaitingFor({ generated_at: report?.generated_at });
    } catch (e) {
      setRefreshNote(e.message);
    }
  }

  const sections = report?.sections || {};
  const tabs = useMemo(() => TABS.filter((t) => t.id === "overview" || sections[t.id]), [sections]);
  const tech = sections.technical?.metrics || {};

  return (
    <AppShell title="Business Intelligence" subtitle="Agent-generated technical, fundamental, news and quantitative intelligence for your configured scripts"
      actions={<TopBar onLogout={onLogout} rightLink={<NavLinks />} />}>
      {list.error ? <Notice tone="rose">{list.error}</Notice> : null}
      {!list.loading && !reports.length && !list.error ? (
        <Notice tone="amber">
          No scripts are set up yet. Add some on the <Link className="underline" to="/admin/bi">BI Setup</Link> page.
        </Notice>
      ) : null}

      <section className="panel relative z-20 mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs uppercase tracking-widest text-slate-400" htmlFor="bi-symbol">Script</label>
          <select id="bi-symbol" className="rounded-xl border border-slate-600 bg-slate-900/70 px-3 py-2 text-sm text-slate-100" value={symbol}
            onChange={(e) => { setParams({ symbol: e.target.value }); setTab("overview"); setRefreshNote(""); }}>
            {reports.map((r) => (
              <option key={r.symbol} value={r.symbol}>
                {r.symbol} · {r.company_name || ""} {r.recommendation ? `· ${RECOMMENDATION_LABEL[r.recommendation]}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          {reports.slice(0, 12).map((r) => (
            <button key={r.symbol} type="button" onClick={() => setParams({ symbol: r.symbol })}
              className={`rounded-full border px-2.5 py-1 text-xs ${r.symbol === symbol ? "border-cyan-400/70 text-cyan-100" : "border-slate-700 text-slate-300 hover:border-slate-500"}`}>
              {r.symbol} <span aria-hidden="true">{RECOMMENDATION_ICON[r.recommendation] || ""}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {refreshNote ? <span className="text-xs text-slate-400">{refreshNote}{waitingFor ? " Waiting…" : ""}</span> : null}
          <button type="button" className="btn-ghost text-sm" disabled={!symbol || !!waitingFor} onClick={regenerate}>Regenerate now</button>
          <Link to="/admin/bi" className="btn-ghost text-sm">Setup</Link>
        </div>
      </section>

      {symbol && detail.data && !detail.data.exists ? (
        <Notice tone="amber">The agents haven't produced a report for {symbol} yet; it appears within a few minutes of saving the setup (or press Regenerate now).</Notice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">
          {report ? (
            <>
              <section className="panel mb-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-widest text-slate-400">{report.sector}</p>
                    <h2 className="font-display text-2xl font-bold text-slate-100">{symbol} <span className="text-base font-normal text-slate-400">{report.company_name}</span></h2>
                    <p className="mt-1 max-w-3xl text-slate-200">{report.headline}</p>
                  </div>
                  <div className="text-right">
                    <RecommendationBadge rec={report.recommendation} large />
                    <p className="mt-2 font-display text-2xl text-slate-100">NPR {num(report.last_price)}</p>
                    <p className="text-sm text-slate-400">{signedPct(tech.change_pct)} {tech.provisional_today ? "· live" : ""}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-slate-400">
                  <span className="flex items-center gap-2">Score <ScoreBar score={report.score} /></span>
                  <span>Confidence <span className="text-slate-200">{num((report.confidence || 0) * 100, 0)}%</span></span>
                  <span>Horizon <span className="text-slate-200">{report.setting?.horizon}</span> · risk <span className="text-slate-200">{report.setting?.risk_profile}</span></span>
                  <span>Updated <span className="text-slate-200" title={shortDateTime(report.generated_at)}>{timeAgo(report.generated_at)}</span></span>
                  <span>Data as of <span className="text-slate-200">{shortDateTime(report.data_as_of)}</span></span>
                  {report.status !== "ok" ? <span className="text-amber-300">⚠ {report.status}</span> : null}
                </div>
                {report.error_text ? <p className="mt-2 text-xs text-amber-300">{report.error_text}</p> : null}
              </section>

              <div className="mb-4 flex flex-wrap gap-2" role="tablist">
                {tabs.map((t) => (
                  <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                    className={tab === t.id ? "btn-ghost border-cyan-400/70 text-cyan-200" : "btn-ghost"}>
                    {t.label}
                  </button>
                ))}
              </div>
              {tab === "overview" ? <Overview report={report} /> : null}
              {tab === "technical" ? <Technical section={sections.technical} /> : null}
              {tab === "fundamental" ? <Fundamental section={sections.fundamental} /> : null}
              {tab === "news" ? <News section={sections.news} /> : null}
              {tab === "quant" ? <Quant section={sections.quant} /> : null}
              <p className="mt-4 text-xs text-slate-500">
                Generated by the BI agents from this platform's market, floor-sheet, fundamentals and news data. Research support, not financial advice.
              </p>
            </>
          ) : detail.loading ? (
            <section className="panel text-slate-400">Loading report…</section>
          ) : null}
        </div>
        <aside className="panel h-fit xl:sticky xl:top-4">
          <ChatPanel symbol={symbol} llmEnabled={list.data?.llm_enabled} />
        </aside>
      </div>
      {summary && !summary.enabled ? <Notice tone="slate">{symbol} is disabled in BI Setup: its report is no longer refreshed.</Notice> : null}
    </AppShell>
  );
}
