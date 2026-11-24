import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SEVERITY_STYLE, apiJson } from "../lib/bi";
import { timeAgo } from "../lib/format";

const POLL_MS = 30000;

// BI automation alerts (price moves, volume spikes, news, recommendation
// changes). Polls the unread count; the dropdown lists the latest alerts.
export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ notifications: [], unread_count: 0 });
  const boxRef = useRef(null);

  async function load() {
    try {
      setData(await apiJson("/bi/notifications?limit=25"));
    } catch {
      /* BI service down: keep the last state */
    }
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    function onDown(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  async function markRead(body) {
    try {
      await apiJson("/bi/notifications/read", "POST", body);
      load();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="relative z-30" ref={boxRef}>
      <button type="button" className="btn-ghost relative px-3" onClick={() => setOpen((o) => !o)} aria-label={`Notifications (${data.unread_count} unread)`}>
        <span aria-hidden="true">🔔</span>
        {data.unread_count ? (
          <span className="absolute -right-1 -top-1 min-w-[1.25rem] rounded-full bg-rose-500 px-1 text-center text-[11px] font-bold text-white">
            {data.unread_count > 99 ? "99+" : data.unread_count}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 mt-2 w-[min(92vw,380px)] rounded-xl border border-slate-700 bg-slate-950/95 p-2 shadow-2xl backdrop-blur">
          <div className="mb-1 flex items-center justify-between px-1">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">BI alerts</p>
            {data.unread_count ? (
              <button type="button" className="text-xs text-cyan-300 hover:underline" onClick={() => markRead({ all: true })}>Mark all read</button>
            ) : null}
          </div>
          <div className="max-h-[420px] space-y-1 overflow-y-auto">
            {!data.notifications.length ? <p className="px-2 py-4 text-center text-sm text-slate-400">No alerts yet.</p> : null}
            {data.notifications.map((n) => {
              const sev = SEVERITY_STYLE[n.severity] || SEVERITY_STYLE.info;
              return (
                <button key={n.id} type="button"
                  className={`block w-full rounded-lg border-l-2 px-2 py-1.5 text-left hover:bg-slate-800/70 ${sev.cls} ${n.read ? "opacity-60" : "bg-slate-900/70"}`}
                  onClick={() => {
                    if (!n.read) markRead({ ids: [n.id] });
                    setOpen(false);
                    if (n.kind === "news" && n.data?.url) window.open(n.data.url, "_blank", "noopener");
                    else if (n.symbol) navigate(`/bi?symbol=${encodeURIComponent(n.symbol)}`);
                  }}>
                  <p className="text-sm text-slate-100">
                    <span aria-hidden="true">{sev.icon} </span>
                    {n.title}
                  </p>
                  {n.body ? <p className="line-clamp-2 text-xs text-slate-400">{n.body}</p> : null}
                  <p className="text-[10px] text-slate-500">{n.severity} · {timeAgo(n.created_at)}</p>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
