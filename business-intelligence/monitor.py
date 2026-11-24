"""The always-on watcher: for every enabled script with alerts on, look at
the live session (price move from the previous close, volume vs. its
20-session average) and new news, write notifications (deduped per event)
and return the scripts whose report should be refreshed now."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import market_data
import store
from common import now_npt, today_npt

NEWS_FRESHNESS = timedelta(hours=6)  # only articles scraped this recently notify (not backfilled old news)


def check_alerts() -> dict[str, Any]:
    settings = [s for s in store.list_settings() if s["enabled"] and s["alerts_enabled"]]
    if not settings:
        return {"checked": 0, "alerts": 0, "refresh": []}
    quotes = market_data.live_quotes([s["symbol"] for s in settings])
    today = today_npt().isoformat()
    now = now_npt()
    created = 0
    refresh: set[str] = set()
    for s in settings:
        sym = s["symbol"]
        q = quotes.get(sym)
        if q and q.get("last_traded_price") and q.get("previous_close"):
            ltp, prev = float(q["last_traded_price"]), float(q["previous_close"])
            chg = (ltp / prev - 1) * 100
            thr = float(s["alert_price_change_pct"])
            steps = int(abs(chg) // thr)
            if steps >= 1:
                direction = "up" if chg > 0 else "down"
                severity = "critical" if abs(chg) >= 9 else "warning" if steps >= 2 else "info"
                if store.add_notification(
                    sym, "price_move", severity, f"{sym} {chg:+.2f}% at NPR {ltp:,.2f}",
                    f"Previous close {prev:,.2f}; volume {int(q.get('volume') or 0):,} shares so far today.",
                    {"price": ltp, "previous_close": prev, "change_pct": chg, "at": q.get("scraped_at")},
                    f"price:{sym}:{today}:{direction}:{steps}",
                ):
                    created += 1
                    refresh.add(sym)
            vol = float(q.get("volume") or 0)
            avg = market_data.average_volume(sym, 20)
            ratio = float(s["alert_volume_spike_ratio"])
            if avg and vol >= ratio * avg:
                if store.add_notification(
                    sym, "volume_spike", "warning", f"{sym} volume {vol / avg:.1f}x its 20-session average",
                    f"{int(vol):,} shares traded today vs. an average of {int(avg):,}.",
                    {"volume": vol, "average": avg, "ratio": vol / avg}, f"volume:{sym}:{today}",
                ):
                    created += 1
                    refresh.add(sym)
        if s["alert_on_news"]:
            info = market_data.security_info(sym) or {}
            terms = [t for t in [market_data.company_core_name(info.get("company_name"))] + list(s.get("news_keywords") or []) if t]
            for a in market_data.news_mentioning(sym, terms, days=2, limit=5, body_chars=300):
                if not a.get("scraped_at") or now - a["scraped_at"] > NEWS_FRESHNESS:
                    continue
                if store.add_notification(
                    sym, "news", "info", f"{sym} in the news: {(a.get('title') or '')[:140]}",
                    f"{a.get('source')} · {a.get('published_at') or a.get('scraped_at')}",
                    {"article_id": a["id"], "url": a.get("url"), "source": a.get("source")}, f"news:{sym}:{a['id']}",
                ):
                    created += 1
                    refresh.add(sym)
    return {"checked": len(settings), "alerts": created, "refresh": sorted(refresh)}
