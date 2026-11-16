import { useEffect, useMemo, useRef, useState } from "react";
import { formatNumber, formatPct, trendColor } from "../lib/format";
import { useApi } from "../lib/useApi";

// Search box for the Technicals page: the 17 indices (filtered locally)
// and every stock with daily history (searched server-side by symbol,
// company name or sector). An empty box lists all indices and the latest
// session's most traded stocks. Arrow keys + Enter pick, Escape closes.
export function SecurityPicker({ indices, selected, onSelect }) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 200);
    return () => window.clearTimeout(id);
  }, [query]);

  const stocks = useApi(open ? `/dashboard/stocks?q=${encodeURIComponent(debounced)}&limit=${debounced ? 25 : 10}` : null);

  const options = useMemo(() => {
    const q = query.trim().toUpperCase();
    const indexOptions = (indices || [])
      .filter((i) => !q || i.index_name.toUpperCase().includes(q))
      .map((i) => ({ kind: "index", id: i.index_name, item: i }));
    const stockOptions = (stocks.data?.stocks || []).map((s) => ({ kind: "stock", id: s.symbol, item: s }));
    return [...indexOptions, ...stockOptions];
  }, [indices, stocks.data, query]);

  useEffect(() => setHighlight(0), [query, open]);

  useEffect(() => {
    function onDown(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function pick(option) {
    onSelect(option.kind, option.id);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, Math.max(options.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && open && options[highlight]) {
      e.preventDefault();
      pick(options[highlight]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  const firstStock = options.findIndex((o) => o.kind === "stock");
  const searching = stocks.loading || debounced !== query.trim();

  return (
    <div ref={boxRef} className="relative w-full max-w-xl">
      <label className="mb-1 block text-xs uppercase tracking-widest text-slate-400" htmlFor="security-search">
        Index or stock
      </label>
      <input
        id="security-search"
        ref={inputRef}
        type="text"
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-expanded={open}
        aria-controls="security-options"
        className="w-full rounded-xl border border-slate-600 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none"
        placeholder={`${selected.id} — search a symbol, company or sector (e.g. NABIL, Upper Tamakoshi, Hydro)`}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open ? (
        <ul
          id="security-options"
          role="listbox"
          className="absolute z-30 mt-1 max-h-[28rem] w-full overflow-auto rounded-xl border border-slate-600 bg-slate-900 py-1 shadow-2xl"
        >
          {options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-slate-400">{searching ? "Searching…" : `No index or stock matches "${query}".`}</li>
          ) : null}
          {options.map((option, i) => (
            <li key={`${option.kind}:${option.id}`} role="option" aria-selected={i === highlight}>
              {i === 0 && option.kind === "index" ? <GroupLabel>Indices</GroupLabel> : null}
              {i === firstStock ? <GroupLabel>{query.trim() ? "Stocks" : "Most traded stocks — type to search all"}</GroupLabel> : null}
              <button
                type="button"
                onMouseEnter={() => setHighlight(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(option)}
                className={`flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm ${
                  i === highlight ? "bg-cyan-500/15" : ""
                } ${option.kind === selected.kind && option.id === selected.id ? "text-cyan-200" : "text-slate-200"}`}
              >
                {option.kind === "index" ? <IndexRow item={option.item} /> : <StockRow item={option.item} />}
              </button>
            </li>
          ))}
          {firstStock === -1 && options.length > 0 && searching ? <li className="px-3 py-2 text-xs text-slate-500">Searching stocks…</li> : null}
        </ul>
      ) : null}
    </div>
  );
}

function GroupLabel({ children }) {
  return <div className="px-3 pb-1 pt-2 text-[11px] uppercase tracking-widest text-slate-500">{children}</div>;
}

function IndexRow({ item }) {
  return (
    <>
      <span className="font-medium">{item.index_name}</span>
      <span className="shrink-0 text-xs text-slate-400">
        {formatNumber(item.latest_value, 2)} · since {item.first_date?.slice(0, 4)}
      </span>
    </>
  );
}

function StockRow({ item }) {
  const badge = item.status && item.status !== "Active" ? item.status : item.type && item.type !== "Equity" ? item.type : null;
  return (
    <>
      <span className="min-w-0">
        <span className="font-semibold">{item.symbol}</span>
        {badge ? <span className="ml-2 rounded bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase text-slate-300">{badge}</span> : null}
        <span className="block truncate text-xs text-slate-400">
          {item.name || "—"}
          {item.sector ? ` · ${item.sector}` : ""}
        </span>
      </span>
      <span className="shrink-0 text-right text-xs">
        <span className="block text-slate-200">{formatNumber(item.close, 2)}</span>
        {item.trading ? (
          <span className={trendColor(item.change_pct)}>{formatPct(item.change_pct, 2, true)}</span>
        ) : (
          <span className="text-slate-500">last {item.last_date}</span>
        )}
      </span>
    </>
  );
}
