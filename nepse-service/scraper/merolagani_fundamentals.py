"""Company fundamentals from merolagani.com's company page
(CompanyDetail.aspx?symbol=X): EPS, P/E, book value, P/BV, the latest cash
dividend / bonus and their history, shares outstanding, market cap,
52-week range. Neither the database nor NEPSE's API carries these.

Plain GET, no auth. The figures are merolagani's: EPS is its annualised
figure for the latest reported quarter (`eps_period`, e.g. "FY:083-084,
Q:1"), P/E = market price / that EPS. Pacing between requests is the
caller's job (capture_company_fundamentals_activity sleeps
MEROLAGANI_REQUEST_PAUSE_SECONDS between symbols).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

URL = "https://merolagani.com/CompanyDetail.aspx"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")
_FY = re.compile(r"FY:\s*([0-9]{3}-[0-9]{3})")
_TRADED_ON = re.compile(r"(\d{4})/(\d{2})/(\d{2})")

# merolagani's collapsible history panels on the company page.
HISTORY_PANELS = {"cash_dividend": "dividend-panel", "bonus": "bonus-panel", "right": "right-panel"}


class FundamentalsNotFound(Exception):
    """merolagani has no company page data for the symbol (e.g. debentures, funds)."""


def _num(text: str | None) -> float | None:
    if not text:
        return None
    m = _NUM.search(text.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _history(soup: BeautifulSoup, panel_id: str) -> list[dict[str, Any]]:
    """Rows of a history panel as [{fiscal_year, value_pct}], in page order
    (newest first). merolagani lists some fiscal years twice (e.g. a 0.00%
    row next to the real one)."""
    panel = soup.find(id=panel_id)
    if panel is None:
        return []
    out = []
    for tr in panel.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        pct_cell = next((c for c in cells if "%" in c), None)
        fy = _FY.search(next((c for c in cells if "FY" in c), ""))
        if pct_cell is None or fy is None:
            continue
        out.append({"fiscal_year": fy.group(1), "value_pct": _num(pct_cell)})
    return out


def parse_company_page(html: str, symbol: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if not th or not td:
            continue
        key = " ".join(th.get_text(" ", strip=True).split())
        if not key or key == "#" or len(key) > 40 or key in fields:
            continue
        fields[key] = " ".join(td.get_text(" ", strip=True).split())
    if "Market Price" not in fields:
        raise FundamentalsNotFound(symbol)

    eps_text = fields.get("EPS", "")
    eps_period = re.search(r"\((FY:[^)]*)\)", eps_text)
    hi_lo = re.findall(r"\d[\d,]*\.?\d*", fields.get("52 Weeks High - Low", "").replace(",", ""))
    traded = _TRADED_ON.search(fields.get("Last Traded On", ""))
    return {
        "symbol": symbol,
        "last_traded_on": date(int(traded.group(1)), int(traded.group(2)), int(traded.group(3))) if traded else None,
        "sector": fields.get("Sector"),
        "market_price": _num(fields.get("Market Price")),
        "eps": _num(eps_text),
        "eps_period": eps_period.group(1) if eps_period else None,
        "pe_ratio": _num(fields.get("P/E Ratio")),
        "book_value": _num(fields.get("Book Value")),
        "pbv": _num(fields.get("PBV")),
        "cash_dividend_pct": _num(fields.get("% Dividend")),
        "bonus_pct": _num(fields.get("% Bonus")),
        "shares_outstanding": _num(fields.get("Shares Outstanding")),
        "market_cap": _num(fields.get("Market Capitalization")),
        "paidup_value": _num(fields.get("Paidup Value")),
        "high_52w": float(hi_lo[0]) if len(hi_lo) >= 2 else None,
        "low_52w": float(hi_lo[1]) if len(hi_lo) >= 2 else None,
        "avg_120d": _num(fields.get("120 Day Average")),
        "avg_180d": _num(fields.get("180 Day Average")),
        "yield_1y_pct": _num(fields.get("1 Year Yield")),
        "avg_volume_30d": _num(fields.get("30-Day Avg Volume")),
        "history": _with_latest({kind: _history(soup, panel) for kind, panel in HISTORY_PANELS.items()}, fields),
    }


def _with_latest(history: dict[str, list[dict[str, Any]]], fields: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """The summary rows ('% Dividend 10.80 (FY:082-083)', '% Bonus 5.00
    (FY:082-083)') carry the latest figure even when the history table
    below them is empty; add it when its fiscal year isn't listed."""
    for kind, key in (("cash_dividend", "% Dividend"), ("bonus", "% Bonus")):
        text = fields.get(key, "")
        fy = _FY.search(text)
        value = _num(text.split("(")[0])
        if fy and value is not None and not any(h["fiscal_year"] == fy.group(1) for h in history[kind]):
            history[kind].insert(0, {"fiscal_year": fy.group(1), "value_pct": value})
    return history


def fetch_company_fundamentals(symbol: str, timeout: int = 30) -> dict[str, Any]:
    """Parsed company page; raises FundamentalsNotFound or requests errors."""
    resp = requests.get(URL, params={"symbol": symbol}, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = parse_company_page(resp.text, symbol)
    data["fetched_at"] = datetime.now()
    return data
