import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { NavLinks } from "../components/NavLinks";
import { Notice, Panel } from "../components/Panel";
import { TopBar } from "../components/TopBar";
import { RECOMMENDATION_ICON, RECOMMENDATION_LABEL, apiJson } from "../lib/bi";
import { timeAgo } from "../lib/format";
import { useApi, useLogout } from "../lib/useApi";

const GROUP_FLAG = { technical: "technical_enabled", fundamental: "fundamental_enabled", news: "news_enabled", quant: "quant_enabled" };

function defaultsFor(feature) {
  return Object.fromEntries((feature.params || []).map((p) => [p.name, p.default]));
}

function ParamInput({ param, value, onChange }) {
  const common = "w-full rounded-lg border border-slate-600 bg-slate-950/60 px-2 py-1 text-sm text-slate-100";
  if (param.type === "bool") return <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />;
  if (param.type === "choice")
    return (
      <select className={common} value={value} onChange={(e) => onChange(e.target.value)}>
        {param.options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  if (param.type === "int_list")
    return <input className={common} value={Array.isArray(value) ? value.join(", ") : value ?? ""} placeholder="e.g. 20, 50, 200"
      onChange={(e) => onChange(e.target.value.split(",").map((v) => v.trim()).filter(Boolean).map(Number))} />;
  return <input className={common} type="number" step={param.type === "float" ? "0.1" : "1"} min={param.min ?? undefined} max={param.max ?? undefined}
    value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />;
}

function AddScript({ existing, onPick }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(q.trim()), 200);
    return () => window.clearTimeout(id);
  }, [q]);
  useEffect(() => {
    const onDown = (e) => box.current && !box.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);
  const stocks = useApi(open ? `/dashboard/stocks?q=${encodeURIComponent(debounced)}&limit=20` : null);
  const options = (stocks.data?.stocks || []).filter((s) => !existing.includes(s.symbol) && (!s.type || s.type === "Equity"));
  return (
    <div className="relative" ref={box}>
      <input className="field py-2 text-sm" placeholder="Add a script: search symbol or company…" value={q}
        onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }} />
      {open ? (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-slate-700 bg-slate-950/95 p-1 shadow-2xl">
          {!options.length ? <p className="px-2 py-2 text-sm text-slate-400">{stocks.loading ? "Searching…" : "No matching equity."}</p> : null}
          {options.map((s) => (
            <button key={s.symbol} type="button" className="block w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-slate-800"
              onClick={() => { onPick(s.symbol); setQ(""); setOpen(false); }}>
              <span className="font-semibold text-slate-100">{s.symbol}</span> <span className="text-slate-400">{s.name}</span>
              <span className="block text-xs text-slate-500">{s.sector}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function BiSetupPage() {
  const onLogout = useLogout();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [tick, setTick] = useState(0);
  const catalog = useApi("/admin/bi/catalog");
  const settings = useApi(`/admin/bi/settings?t=${tick}`);
  const reports = useApi(`/bi/reports?t=${tick}`, 60000);
  const [form, setForm] = useState(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ tone: "", text: "" });
  const selected = (params.get("symbol") || "").toUpperCase();
  const list = settings.data?.settings || [];
  const reportBy = useMemo(() => Object.fromEntries((reports.data?.reports || []).map((r) => [r.symbol, r])), [reports.data]);
  const cat = catalog.data;

  // Load the selected script's setup into the form (or catalog defaults for a new one).
  useEffect(() => {
    if (!selected || !cat) return;
    const existing = list.find((s) => s.symbol === selected);
    if (existing) {
      setForm(JSON.parse(JSON.stringify(existing)));
      setIsNew(false);
    } else if (settings.data) {
      setForm({ ...JSON.parse(JSON.stringify(cat.defaults)), symbol: selected });
      setIsNew(true);
    }
    setMessage({ tone: "", text: "" });
  }, [selected, cat, settings.data]); // eslint-disable-line react-hooks/exhaustive-deps

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }
  function toggleFeature(group, feature, on) {
    setForm((f) => {
      const g = { ...(f.features[group] || {}) };
      if (on) g[feature.id] = defaultsFor(feature);
      else delete g[feature.id];
      return { ...f, features: { ...f.features, [group]: g } };
    });
  }
  // Preset for one agent's features: "basic" (the defaults), "all" or "none".
  function preset(group, mode) {
    const g = cat.groups.find((x) => x.id === group);
    const picked = g.features.filter((f) => mode === "all" || (mode === "basic" && f.level === "basic"));
    setForm((f) => {
      const current = f.features[group] || {};
      // keep the parameters already set for features that stay on
      const next = Object.fromEntries(picked.map((feat) => [feat.id, current[feat.id] || defaultsFor(feat)]));
      return { ...f, features: { ...f.features, [group]: next } };
    });
  }
  function resetToDefaults() {
    const d = cat.defaults;
    setForm((f) => ({
      ...f,
      features: JSON.parse(JSON.stringify(d.features)),
      technical_enabled: d.technical_enabled, fundamental_enabled: d.fundamental_enabled, news_enabled: d.news_enabled, quant_enabled: d.quant_enabled,
    }));
    setMessage({ tone: "ok", text: "Analyses reset to the defaults (all basic features). Press Save to apply." });
  }
  function setParam(group, fid, name, value) {
    setForm((f) => ({ ...f, features: { ...f.features, [group]: { ...f.features[group], [fid]: { ...f.features[group][fid], [name]: value } } } }));
  }

  async function save() {
    setSaving(true);
    setMessage({ tone: "", text: "" });
    try {
      const saved = await apiJson(`/admin/bi/settings/${encodeURIComponent(form.symbol)}`, "PUT", form);
      setForm(saved);
      setIsNew(false);
      setTick((t) => t + 1);
      setMessage({ tone: "ok", text: `Saved. The agents are generating ${saved.symbol}'s report now.` });
    } catch (e) {
      if (e.status === 401) navigate("/login", { replace: true });
      setMessage({ tone: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Remove ${form.symbol} from business intelligence? Its report is deleted too.`)) return;
    try {
      await apiJson(`/admin/bi/settings/${encodeURIComponent(form.symbol)}`, "DELETE");
      setParams({});
      setForm(null);
      setTick((t) => t + 1);
    } catch (e) {
      setMessage({ tone: "error", text: e.message });
    }
  }

  const levelBadge = (level) =>
    level === "advanced" ? (
      <span className="ml-1 rounded bg-violet-500/20 px-1.5 text-[10px] uppercase text-violet-200">advanced</span>
    ) : (
      <span className="ml-1 rounded bg-slate-700/60 px-1.5 text-[10px] uppercase text-slate-300">basic</span>
    );

  return (
    <AppShell title="BI Setup" subtitle="Choose the scripts the agents analyse 24/7, and which indicators, metrics and alerts each one gets"
      actions={<TopBar onLogout={onLogout} rightLink={<NavLinks />} />}>
      {[catalog.error, settings.error].filter(Boolean).map((e) => <Notice key={e} tone="rose">{e}</Notice>)}
      {cat && !cat.llm_enabled ? (
        <Notice tone="amber">
          No LLM is configured for the BI service, so summaries are rule-based and Q&A is off. Set BI_LLM_MODEL with BI_LLM_API_KEY (OpenAI) or
          BI_LLM_BASE_URL (any OpenAI-compatible server) in .env.
        </Notice>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="panel h-fit">
          <h3 className="mb-2 font-display text-xl font-semibold">Scripts</h3>
          <AddScript existing={list.map((s) => s.symbol)} onPick={(sym) => setParams({ symbol: sym })} />
          <ul className="mt-3 space-y-1">
            {list.map((s) => {
              const r = reportBy[s.symbol];
              return (
                <li key={s.symbol}>
                  <button type="button" onClick={() => setParams({ symbol: s.symbol })}
                    className={`w-full rounded-xl border px-3 py-2 text-left ${s.symbol === selected ? "border-cyan-400/70 bg-cyan-500/10" : "border-slate-700 hover:border-slate-500"}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-100">{s.symbol}</span>
                      <span className="text-xs text-slate-400">
                        {s.enabled ? (r?.recommendation ? `${RECOMMENDATION_ICON[r.recommendation]} ${RECOMMENDATION_LABEL[r.recommendation]}` : r?.status || "pending") : "disabled"}
                      </span>
                    </div>
                    <p className="truncate text-xs text-slate-400">{s.company_name}</p>
                    {r?.generated_at ? <p className="text-[10px] text-slate-500">report {timeAgo(r.generated_at)}</p> : null}
                  </button>
                </li>
              );
            })}
            {!list.length && !settings.loading ? <p className="text-sm text-slate-400">None yet: search above to add one.</p> : null}
          </ul>
        </aside>

        <div className="min-w-0">
          {!form || !cat ? (
            <section className="panel text-slate-400">Select a script on the left, or add one.</section>
          ) : (
            <div className="grid gap-4">
              <section className="panel flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-display text-2xl font-bold">{form.symbol} <span className="text-base font-normal text-slate-400">{form.company_name || ""}</span></h2>
                  <p className="text-xs text-slate-400">{isNew ? "New setup (not saved yet)" : `Last saved ${timeAgo(form.updated_at)}${form.updated_by ? ` by ${form.updated_by}` : ""}`}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!isNew ? <Link className="btn-ghost text-sm" to={`/bi?symbol=${form.symbol}`}>View report</Link> : null}
                  <button type="button" className="btn-ghost text-sm" onClick={resetToDefaults} title="Turn on every basic feature (default parameters) and all four agents">Reset to defaults</button>
                  {!isNew ? <button type="button" className="btn-ghost text-sm text-rose-200" onClick={remove}>Remove</button> : null}
                  <button type="button" className="btn-primary text-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : isNew ? "Add & generate" : "Save"}</button>
                </div>
                {message.text ? <p className={`w-full text-sm ${message.tone === "error" ? "text-rose-300" : "text-emerald-300"}`}>{message.text}</p> : null}
              </section>

              <Panel title="General">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Agents active</label>
                  {[["horizon", "Horizon"], ["risk_profile", "Risk profile"], ["price_basis", "Price basis"]].map(([k, l]) => (
                    <label key={k} className="text-xs uppercase tracking-widest text-slate-400">{l}
                      <select className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950/60 px-2 py-1.5 text-sm normal-case tracking-normal text-slate-100"
                        value={form[k]} onChange={(e) => set(k, e.target.value)}>
                        {(cat.general[k] || []).map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    </label>
                  ))}
                  {[["lookback_days", "Chart history (days)", 30, 3650], ["refresh_minutes_live", "Refresh in session (min)", 5, 240], ["refresh_minutes_offhours", "Refresh off-hours (min)", 15, 1440]].map(([k, l, lo, hi]) => (
                    <label key={k} className="text-xs uppercase tracking-widest text-slate-400">{l}
                      <input type="number" min={lo} max={hi} className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950/60 px-2 py-1.5 text-sm text-slate-100"
                        value={form[k]} onChange={(e) => set(k, Number(e.target.value))} />
                    </label>
                  ))}
                </div>
              </Panel>

              {cat.groups.map((g) => {
                const flag = GROUP_FLAG[g.id];
                const on = form[flag];
                const active = form.features[g.id] || {};
                return (
                  <Panel key={g.id} title={g.label} note={`${g.agent} · ${g.description}`}
                    right={
                      <div className="flex flex-wrap items-center gap-2">
                        {on ? (
                          <div className="flex overflow-hidden rounded-lg border border-slate-600 text-xs" role="group" aria-label={`${g.label} presets`}>
                            {[["basic", "Basic"], ["all", "All"], ["none", "None"]].map(([mode, lbl]) => (
                              <button key={mode} type="button" className="px-2.5 py-1 text-slate-300 hover:bg-slate-800 hover:text-slate-100" onClick={() => preset(g.id, mode)}
                                title={mode === "basic" ? "Check the basic features (the defaults)" : mode === "all" ? "Check every feature, advanced included" : "Uncheck everything"}>
                                {lbl}
                              </button>
                            ))}
                          </div>
                        ) : null}
                        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={on} onChange={(e) => set(flag, e.target.checked)} /> Run this agent</label>
                      </div>
                    }>
                    <p className="mb-2 text-xs text-slate-500">
                      {Object.keys(active).length} of {g.features.length} on · basic features are checked by default, advanced ones are optional extras.
                    </p>
                    <div className={`grid gap-2 md:grid-cols-2 ${on ? "" : "pointer-events-none opacity-40"}`}>
                      {g.features.map((f) => {
                        const fOn = f.id in active;
                        return (
                          <div key={f.id} className={`rounded-xl border p-3 ${fOn ? "border-cyan-500/40 bg-cyan-950/10" : "border-slate-700/70"}`}>
                            <label className="flex items-start gap-2">
                              <input type="checkbox" className="mt-1" checked={fOn} onChange={(e) => toggleFeature(g.id, f, e.target.checked)} />
                              <span>
                                <span className="text-sm font-medium text-slate-100">{f.label}</span>{levelBadge(f.level)}
                                <span className="block text-xs text-slate-400">{f.description}</span>
                              </span>
                            </label>
                            {fOn && f.params.length ? (
                              <div className="mt-2 grid grid-cols-2 gap-2 pl-6">
                                {f.params.map((p) => (
                                  <label key={p.name} className="text-[11px] text-slate-400">{p.label}
                                    <ParamInput param={p} value={active[f.id]?.[p.name]} onChange={(v) => setParam(g.id, f.id, p.name, v)} />
                                  </label>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                    {g.id === "news" ? (
                      <label className="mt-3 block text-xs uppercase tracking-widest text-slate-400">Extra news keywords (comma-separated, e.g. the Nepali name)
                        <input className="field mt-1 py-2 text-sm normal-case tracking-normal" value={(form.news_keywords || []).join(", ")}
                          onChange={(e) => set("news_keywords", e.target.value.split(",").map((v) => v.trim()).filter(Boolean))} />
                      </label>
                    ) : null}
                  </Panel>
                );
              })}

              <Panel title="Alerts" note="Raised by the monitor every minute; shown in the 🔔 menu">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.alerts_enabled} onChange={(e) => set("alerts_enabled", e.target.checked)} /> Alerts on</label>
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.alert_on_signal_change} onChange={(e) => set("alert_on_signal_change", e.target.checked)} /> Recommendation changes</label>
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.alert_on_news} onChange={(e) => set("alert_on_news", e.target.checked)} /> New news</label>
                  <label className="text-xs uppercase tracking-widest text-slate-400">Price move from previous close (%)
                    <input type="number" step="0.5" min={0.5} max={10} className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950/60 px-2 py-1.5 text-sm text-slate-100"
                      value={form.alert_price_change_pct} onChange={(e) => set("alert_price_change_pct", Number(e.target.value))} />
                  </label>
                  <label className="text-xs uppercase tracking-widest text-slate-400">Volume vs. 20-session average (x)
                    <input type="number" step="0.5" min={1.2} max={20} className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950/60 px-2 py-1.5 text-sm text-slate-100"
                      value={form.alert_volume_spike_ratio} onChange={(e) => set("alert_volume_spike_ratio", Number(e.target.value))} />
                  </label>
                </div>
              </Panel>

              <Panel title="Summary & instructions">
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.llm_summary_enabled} onChange={(e) => set("llm_summary_enabled", e.target.checked)} /> LLM writes the summary and rates news (off = rule-based)</label>
                <label className="mt-3 block text-xs uppercase tracking-widest text-slate-400">Instructions for the agents (optional)
                  <textarea className="field mt-1 min-h-[80px] py-2 text-sm normal-case tracking-normal" maxLength={2000} placeholder="e.g. I hold 500 shares bought at 520; focus on dividend safety."
                    value={form.custom_instructions || ""} onChange={(e) => set("custom_instructions", e.target.value)} />
                </label>
              </Panel>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
