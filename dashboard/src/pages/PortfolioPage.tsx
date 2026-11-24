import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { NavLinks } from "../components/NavLinks";
import { Metric, Notice, Panel } from "../components/Panel";
import { TopBar } from "../components/TopBar";
import { Fan, FrontierChart, GroupedBars, Histogram, SeriesLine } from "../components/bi/BiCharts";
import { MiniMarkdown } from "../components/bi/MiniMarkdown";
import { API_BASE } from "../lib/api";
import { SERIES, apiJson, num, signedPct } from "../lib/bi";
import { formatCompact, shortDateTime, timeAgo } from "../lib/format";
import { useLogout } from "../lib/useApi";

const HORIZONS = [
  { value: "1M", label: "1 month" },
  { value: "3M", label: "3 months" },
  { value: "6M", label: "6 months" },
  { value: "1Y", label: "1 year" },
];
const DEFAULT_FORM = {
  budget: 500000, horizon: "3M", target_return_pct: 8, risk_profile: "moderate", universe: "liquid", universe_size: 40,
  max_weight_pct: "", max_sector_pct: "", lot_size: 10, cost_pct: 0.45, holdings: [], exclude: "",
};
const ACTION_STYLE = { buy: "text-emerald-300", increase: "text-emerald-300", sell: "text-rose-300", reduce: "text-rose-300", hold: "text-slate-300" };

// POST the request and read the agent's SSE stream: progress / result / error.
async function optimizeStream(body, onEvent, signal) {
  const res = await fetch(`${API_BASE}/bi/portfolio/optimize`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  });
  if (!res.ok || !res.body) {
    const error = new Error(`Request failed (${res.status})`) as Error & { status?: number };
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
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent(event, JSON.parse(data));
    }
  }
}

function Results({ row }) {
  const r = row.result;
  const p = r.portfolio;
  const req = r.request;
  const risk = r.risk || {};
  const n = r.narrative || {};
  const allocs = r.allocations || [];
  const held = allocs.filter((a) => a.shares > 0);
  const horizonLabel = HORIZONS.find((h) => h.value === req.horizon)?.label || req.horizon;
  return (
    <div className="grid gap-4">
      {!p.target_reachable ? (
        <Notice tone="amber">
          A {num(req.target_return_pct, 1)}% return in {horizonLabel} is above what the analytics support with your caps: the best expected return is
          {" "}{num(p.max_achievable_return_pct, 2)}%. This is the maximum-return portfolio; lower the target or lengthen the horizon for a lower-risk one.
        </Notice>
      ) : null}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Expected return" value={signedPct(p.expected_return_pct)} sub={`NPR ${num(p.expected_profit, 0)} over ${horizonLabel}`} tone="text-cyan-100" />
        <Metric label="Chance of reaching target" value={`${num(p.probability_reach_target_pct, 0)}%`} sub={`target ${num(req.target_return_pct, 1)}%`} />
        <Metric label="Chance of a loss" value={`${num(p.probability_loss_pct, 0)}%`} sub={`volatility ${num(p.volatility_pct, 1)}%`} />
        <Metric label="95% Value at Risk" value={`NPR ${formatCompact(p.var_95_amount)}`} sub={`${num(p.var_95_pct, 1)}% · CVaR ${num(p.cvar_95_pct, 1)}%`} />
        <Metric label="Typical max drawdown" value={`${num(p.expected_max_drawdown_pct, 1)}%`} sub={`bad case ${num(p.bad_case_max_drawdown_pct, 1)}%`} />
        <Metric label="Beta to NEPSE" value={num(p.beta_nepse, 2)} sub={`NEPSE −10% → ${num(p.nepse_minus_10_impact_pct, 1)}%`} />
        <Metric label="Invested" value={`NPR ${formatCompact(p.invested)}`} sub={`${p.positions} scripts · cash ${formatCompact(p.cash_left)}`} />
        <Metric label="Sharpe (horizon)" value={num(p.sharpe, 2)} sub={`${num(p.effective_positions, 1)} effective positions · fees ~NPR ${num(p.estimated_fees, 0)}`} />
      </section>

      <Panel title="The plan" note={row.llm_used ? `Explained by ${row.llm_model || "the LLM"}` : "Rule-based explanation"}>
        <MiniMarkdown text={n.summary} />
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-400">Target</p><MiniMarkdown text={n.target_assessment} /></div>
          <div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-400">Risk</p><MiniMarkdown text={n.risk_assessment} /></div>
        </div>
        {n.suggestions?.length ? (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-300">{n.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
        ) : null}
      </Panel>

      <Panel title="Orders" note={`Whole lots of ${r.assumptions?.lot_size} shares at the latest prices; trades are relative to your current holdings`}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-xs uppercase tracking-wider text-slate-400">
                <th className="py-2 pr-2">Action</th><th className="pr-2">Script</th><th className="pr-2 text-right">Shares</th><th className="pr-2 text-right">Price</th>
                <th className="pr-2 text-right">Amount</th><th className="pr-2 text-right">Weight</th><th className="pr-2 text-right">Exp. return</th>
                <th className="pr-2 text-right">Risk share</th><th className="pr-2">Why</th>
              </tr>
            </thead>
            <tbody>
              {allocs.map((a) => {
                const why = (n.rationale || []).find((x) => x.symbol === a.symbol)?.reason || a.factors?.slice(0, 2).join("; ");
                return (
                  <tr key={a.symbol} className="border-b border-slate-800/80 align-top">
                    <td className={`py-2 pr-2 font-semibold uppercase ${ACTION_STYLE[a.action]}`}>
                      {a.action}{a.trade_shares ? ` ${Math.abs(a.trade_shares)}` : ""}
                    </td>
                    <td className="pr-2"><span className="font-semibold text-slate-100">{a.symbol}</span><span className="block text-xs text-slate-400">{a.sector}</span></td>
                    <td className="pr-2 text-right font-mono">{num(a.shares, 0)}</td>
                    <td className="pr-2 text-right font-mono">{num(a.price)}</td>
                    <td className="pr-2 text-right font-mono">{num(a.amount, 0)}</td>
                    <td className="pr-2 text-right">{num(a.weight_pct, 1)}%</td>
                    <td className="pr-2 text-right">{signedPct(a.expected_return_pct, 1)}</td>
                    <td className="pr-2 text-right">{a.risk_contribution_pct != null ? `${num(a.risk_contribution_pct, 0)}%` : "-"}</td>
                    <td className="max-w-[320px] pr-2 text-xs text-slate-300">
                      <span className="text-slate-500">score {a.score > 0 ? "+" : ""}{num(a.score, 0)} ({a.score_source}) · </span>{why}
                      {a.days_to_build > 1 ? <span className="block text-amber-300">⚠ ~{num(a.days_to_build, 1)} sessions to build at 10% of daily turnover</span> : null}
                    </td>
                  </tr>
                );
              })}
              {(r.sells || []).map((s) => (
                <tr key={`sell-${s.symbol}`} className="border-b border-slate-800/80">
                  <td className="py-2 pr-2 font-semibold uppercase text-rose-300">review</td>
                  <td className="pr-2 font-semibold text-slate-100">{s.symbol}</td>
                  <td className="pr-2 text-right font-mono">{num(s.shares, 0)}</td>
                  <td colSpan={6} className="pr-2 text-xs text-slate-400">{s.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Allocation" note="Share of capital per script">
          <GroupedBars data={held.map((a) => ({ symbol: a.symbol, weight: a.weight_pct }))} xKey="symbol" layout="vertical" unit="%"
            height={Math.max(180, held.length * 28)} series={[{ key: "weight", name: "Weight" }]} />
        </Panel>
        <Panel title="Risk vs. return" note="Efficient frontier of the candidate scripts (lowest risk for each expected return), with your portfolio">
          <FrontierChart frontier={r.frontier} chosen={r.chosen_point} target={req.target_return_pct} />
        </Panel>
        <Panel title="Simulated value over the horizon" note="Block-bootstrap Monte Carlo of the scripts' joint daily returns, centred on the expected return">
          <Fan xs={(risk.simulated_paths_pct?.p50 || []).map((_, i) => i + 1)} p={risk.simulated_paths_pct} unit="%" xLabel={(x) => `day ${x}`}
            refY={req.target_return_pct} refLabel={`target ${num(req.target_return_pct, 1)}%`} />
        </Panel>
        <Panel title="Distribution of outcomes" note={`Return at the end of ${horizonLabel} across 4,000 simulations`}>
          <Histogram centers={risk.outcome_histogram?.centers} counts={risk.outcome_histogram?.counts} marker={req.target_return_pct} markerLabel="target" />
        </Panel>
        {risk.historical_replay?.dates?.length ? (
          <Panel title="Historical replay" note={`These weights over the last year: ${signedPct(risk.historical_replay.return_pct, 1)}, max drawdown ${num(risk.historical_replay.max_drawdown_pct, 1)}%; worst ${horizonLabel} window ${signedPct(risk.historical_replay.worst_window_pct, 1)}`}>
            <SeriesLine dates={risk.historical_replay.dates} values={risk.historical_replay.cumulative_pct} name="Cumulative return" unit="%" refY={0} />
          </Panel>
        ) : null}
        <Panel title="Sector exposure" note={`Sector cap ${num(r.assumptions?.max_sector_pct, 0)}% · script cap ${num(r.assumptions?.max_weight_pct, 0)}%`}>
          <GroupedBars data={(r.sector_exposure || []).map((s) => ({ sector: s.sector, weight: s.weight_pct }))} xKey="sector" layout="vertical" unit="%"
            height={Math.max(160, (r.sector_exposure || []).length * 30)} series={[{ key: "weight", name: "Weight", color: SERIES[2] }]} />
        </Panel>
      </div>

      <Panel title="Alternatives" note="Other optimal portfolios from the same analytics (weights before lot rounding)">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead><tr className="border-b border-slate-700 text-xs uppercase tracking-wider text-slate-400">
              <th className="py-2">Portfolio</th><th className="text-right">Exp. return</th><th className="text-right">Volatility</th><th className="text-right">Sharpe</th><th className="pl-3">Top weights</th>
            </tr></thead>
            <tbody>
              {Object.entries(r.alternatives || {}).map(([k, a]: [string, any]) => (
                <tr key={k} className="border-b border-slate-800/80">
                  <td className="py-2 text-slate-200">{{ max_sharpe: "Best risk-adjusted (max Sharpe)", min_variance: "Lowest risk", max_return: "Highest return" }[k] || k}</td>
                  <td className="text-right">{signedPct(a.expected_return_pct)}</td>
                  <td className="text-right">{num(a.volatility_pct, 1)}%</td>
                  <td className="text-right">{num(a.sharpe, 2)}</td>
                  <td className="pl-3 text-xs text-slate-400">{(a.weights || []).slice(0, 5).map((w) => `${w.symbol} ${num(w.weight_pct, 0)}%`).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <p className="text-xs text-slate-500">
        Model: {r.assumptions?.expected_return}; covariance {r.assumptions?.covariance}; {r.universe?.modelled} scripts modelled from {r.universe?.considered}
        {" "}candidates; costs {num(r.assumptions?.cost_pct_per_side, 2)}% per side; data as of {r.as_of}. Expected returns are model estimates from
        historical data and analytics, not guarantees. Research support, not financial advice.
      </p>
    </div>
  );
}

export function PortfolioPage() {
  const onLogout = useLogout();
  const navigate = useNavigate();
  const [form, setForm] = useState(DEFAULT_FORM);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [row, setRow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState([]);
  const [error, setError] = useState("");
  const abortRef = useRef(null);

  async function loadCached() {
    try {
      const data = await apiJson("/bi/portfolio");
      if (data.exists) {
        setRow(data.portfolio);
        const req = data.portfolio.request || {};
        setForm((f) => ({ ...f, ...req, exclude: (req.exclude || []).join(", "), max_weight_pct: req.max_weight_pct ?? "", max_sector_pct: req.max_sector_pct ?? "" }));
      }
      return data.portfolio;
    } catch (e) {
      if (e.status === 401) navigate("/login", { replace: true });
      else setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCached();
    return () => abortRef.current?.abort();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // A run started earlier (e.g. before a page reload) is still going: poll until it lands.
  useEffect(() => {
    if (running || row?.status !== "running") return undefined;
    const id = window.setInterval(loadCached, 3000);
    return () => window.clearInterval(id);
  }, [row, running]); // eslint-disable-line react-hooks/exhaustive-deps

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function run(e) {
    e.preventDefault();
    setError("");
    setProgress([]);
    setRunning(true);
    const body = {
      ...form,
      budget: Number(form.budget), target_return_pct: Number(form.target_return_pct), universe_size: Number(form.universe_size),
      lot_size: Number(form.lot_size), cost_pct: Number(form.cost_pct),
      max_weight_pct: form.max_weight_pct === "" ? null : Number(form.max_weight_pct),
      max_sector_pct: form.max_sector_pct === "" ? null : Number(form.max_sector_pct),
      exclude: String(form.exclude || "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean),
      holdings: form.holdings.filter((h) => h.symbol && Number(h.quantity) > 0).map((h) => ({ symbol: h.symbol.toUpperCase(), quantity: Number(h.quantity) })),
    };
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await optimizeStream(body, (event, data) => {
        if (event === "progress") setProgress((p) => [...p.filter((x) => x.stage !== data.stage), data]);
        else if (event === "result") setRow(data.portfolio);
        else if (event === "error") setError(data.message);
      }, controller.signal);
    } catch (err) {
      if (err.status === 401) navigate("/login", { replace: true });
      else if (err.name !== "AbortError") {
        setError(`${err.message}. The optimisation keeps running in the background; its result will show here.`);
        loadCached();
      }
    } finally {
      setRunning(false);
    }
  }

  const last = progress[progress.length - 1];
  const fieldCls = "mt-1 w-full rounded-lg border border-slate-600 bg-slate-950/60 px-2 py-1.5 text-sm text-slate-100";
  return (
    <AppShell title="Portfolio Optimiser" subtitle="Give a budget, a horizon and a target return: the portfolio agent finds the lowest-risk mix of scripts expected to get there, with a full risk analysis"
      actions={<TopBar onLogout={onLogout} rightLink={<NavLinks />} />}>
      <form className="panel relative z-10 mb-4" onSubmit={run}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-xs uppercase tracking-widest text-slate-400">Budget (NPR)
            <input type="number" min={5000} step={1000} required className={fieldCls} value={form.budget} onChange={(e) => set("budget", e.target.value)} />
          </label>
          <label className="text-xs uppercase tracking-widest text-slate-400">Time horizon
            <select className={fieldCls} value={form.horizon} onChange={(e) => set("horizon", e.target.value)}>
              {HORIZONS.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
            </select>
          </label>
          <label className="text-xs uppercase tracking-widest text-slate-400">Target return (%)
            <input type="number" step="0.5" min={-20} max={300} required className={fieldCls} value={form.target_return_pct} onChange={(e) => set("target_return_pct", e.target.value)} />
          </label>
          <label className="text-xs uppercase tracking-widest text-slate-400">Risk profile
            <select className={fieldCls} value={form.risk_profile} onChange={(e) => set("risk_profile", e.target.value)}>
              {["conservative", "moderate", "aggressive"].map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button type="submit" className="btn-primary flex-1" disabled={running}>{running ? "Optimising…" : "Optimise"}</button>
            {running ? <button type="button" className="btn-ghost" onClick={() => abortRef.current?.abort()} title="Stop listening (the run continues in the background)">✕</button> : null}
          </div>
        </div>
        <button type="button" className="mt-3 text-xs text-cyan-300 hover:underline" onClick={() => setShowAdvanced((s) => !s)}>
          {showAdvanced ? "Hide" : "Show"} advanced options & current holdings
        </button>
        {showAdvanced ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-xs uppercase tracking-widest text-slate-400">Universe
              <select className={fieldCls} value={form.universe} onChange={(e) => set("universe", e.target.value)}>
                <option value="liquid">Most traded + BI scripts</option>
                <option value="bi">Only BI-configured scripts</option>
              </select>
            </label>
            <label className="text-xs uppercase tracking-widest text-slate-400">Candidates (most traded)
              <input type="number" min={10} max={80} className={fieldCls} value={form.universe_size} onChange={(e) => set("universe_size", e.target.value)} />
            </label>
            <label className="text-xs uppercase tracking-widest text-slate-400">Max per script (%)
              <input type="number" min={5} max={100} placeholder="by risk profile" className={fieldCls} value={form.max_weight_pct} onChange={(e) => set("max_weight_pct", e.target.value)} />
            </label>
            <label className="text-xs uppercase tracking-widest text-slate-400">Max per sector (%)
              <input type="number" min={10} max={100} placeholder="by risk profile" className={fieldCls} value={form.max_sector_pct} onChange={(e) => set("max_sector_pct", e.target.value)} />
            </label>
            <label className="text-xs uppercase tracking-widest text-slate-400">Lot size (shares)
              <input type="number" min={1} max={100} className={fieldCls} value={form.lot_size} onChange={(e) => set("lot_size", e.target.value)} />
            </label>
            <label className="text-xs uppercase tracking-widest text-slate-400">Trading cost per side (%)
              <input type="number" min={0} max={3} step="0.05" className={fieldCls} value={form.cost_pct} onChange={(e) => set("cost_pct", e.target.value)} />
            </label>
            <label className="text-xs uppercase tracking-widest text-slate-400 lg:col-span-2">Exclude scripts (comma-separated)
              <input className={fieldCls} value={form.exclude} onChange={(e) => set("exclude", e.target.value)} />
            </label>
            <div className="sm:col-span-2 lg:col-span-4">
              <p className="text-xs uppercase tracking-widest text-slate-400">Current holdings (to get buy / sell orders)</p>
              {form.holdings.map((h, i) => (
                <div key={i} className="mt-1 flex gap-2">
                  <input className="field w-40 py-1.5 text-sm" placeholder="Symbol" value={h.symbol}
                    onChange={(e) => set("holdings", form.holdings.map((x, j) => (j === i ? { ...x, symbol: e.target.value.toUpperCase() } : x)))} />
                  <input className="field w-32 py-1.5 text-sm" type="number" min={1} placeholder="Shares" value={h.quantity}
                    onChange={(e) => set("holdings", form.holdings.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} />
                  <button type="button" className="btn-ghost px-3 py-1" onClick={() => set("holdings", form.holdings.filter((_, j) => j !== i))}>✕</button>
                </div>
              ))}
              <button type="button" className="mt-2 text-xs text-cyan-300 hover:underline" onClick={() => set("holdings", [...form.holdings, { symbol: "", quantity: "" }])}>+ Add holding</button>
            </div>
          </div>
        ) : null}
        {running || (row?.status === "running" && !running) ? (
          <div className="mt-4">
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div className="h-2 rounded-full bg-cyan-400 transition-all" style={{ width: `${Math.round((last?.fraction || 0.02) * 100)}%` }} />
            </div>
            <p className="mt-1 text-xs text-slate-300">{last?.message || "Starting the portfolio agent…"}</p>
          </div>
        ) : null}
        {error ? <p className="mt-3 text-sm text-rose-300">⚠ {error}</p> : null}
      </form>

      {loading ? <section className="panel text-slate-400">Loading your last optimisation…</section> : null}
      {!loading && !row ? <Notice tone="slate">No optimisation yet: enter a budget, horizon and target return, then press Optimise.</Notice> : null}
      {row?.status === "failed" ? <Notice tone="rose">The last optimisation failed: {row.error_text}</Notice> : null}
      {row?.status === "ok" && row.result ? (
        <>
          <p className="mb-2 text-xs text-slate-400">
            Result from {shortDateTime(row.completed_at)} ({timeAgo(row.completed_at)}, took {num((row.generation_ms || 0) / 1000, 1)} s). It stays here until you run a new optimisation.
          </p>
          <Results row={row} />
        </>
      ) : null}
    </AppShell>
  );
}
