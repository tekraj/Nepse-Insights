# NEPSE News & Market Data Pipeline

A real-time pipeline that scrapes 20 Nepali news portals and NEPSE live market index every 30 minutes. Built for analyzing news and market data that impacts the Nepal Stock Exchange (NEPSE).

---

## What This Project Does

1. Every 30 minutes, scrapes 20 Nepali news portals
2. Saves articles (title, body, category, source) to PostgreSQL
3. Scrapes NEPSE main index + selected sector indices from Merolagani
4. Saves all index data to PostgreSQL
5. Exposes results via a REST API
6. Serves a React dashboard via Nginx for market/news monitoring

---

## News Portals Scraped (20 total)

### Tier 1 — Finance and NEPSE Focused
Merolagani, Sharesansar, Nepsealpha, NepseKhabar, Nepali Paisa, Karobar Daily, Arthik Abhiyan, Biznews Nepal, Stock Nepali, NEPSE Trading

### Tier 2 — General News (Politics, Economy, Policy)
Onlinekhabar, Setopati, Ratopati, Ekantipur, Nagarik News, The Himalayan Times, MyRepublica, Republica, Annapurna Post, Nepal Live

---

## NEPSE Sector Indices Tracked
Banking, Development Bank, Finance, Hydropower, Insurance, Microfinance, Manufacturing, Investment, Hotel, Trading

---

## Technology Used

| Technology | Purpose |
|---|---|
| Python 3.14 | Main programming language |
| BeautifulSoup4 | Web scraping |
| PostgreSQL | Database |
| FastAPI | REST API |
| APScheduler | Runs every 30 minutes automatically |
| Docker | Deployment |

---

## Project Structure

```
nepali-news-pipeline/
│
├── config/
│   ├── __init__.py
│   └── config.py              # Settings from environment variables
│
├── db/
│   ├── __init__.py
│   ├── connection.py          # PostgreSQL connection + creates tables
│   └── writer.py              # Saves news articles and NEPSE index data
│
├── scraper/
│   ├── __init__.py
│   ├── scrapers.py            # 20 portal scrapers using BeautifulSoup
│   ├── nepse_scraper.py       # NEPSE live index + sector index scraper
│   └── scheduler.py           # Runs full pipeline every 30 minutes
│
├── main.py                    # FastAPI — starts scheduler + API endpoints
├── Dockerfile                 # Server setup instructions
├── docker-compose.yml         # Runs pipeline + PostgreSQL together
├── pyproject.toml             # Python dependencies (dev venv; each service has its own)
├── .env.example               # Environment variable template
└── .gitignore
```

---

## Database Tables

Table names start with the subsystem that owns them (`market_`, `news_`,
`pipeline_`, `app_`); market tables end with their granularity (`_snapshot` =
one row per live scrape, `_daily` = one row per trading day, `_tick` = point
observations). Every table carries a description: run `\dt+` / `\d+ <table>`
in psql. All timestamps are naive Nepal time (NPT).

| Table | What one row is |
|---|---|
| `market_index_snapshot` | One index's value at one live scrape (every minute during market hours) |
| `market_index_daily` | One index's OHLC bar for one trading day (NEPSE since 2000; its rows are the trading calendar) |
| `market_intraday_tick` | One historical intraday price observation of an index or equity (since 2018) |
| `market_price_snapshot` | One security's session-to-date prices/volume at one live scrape |
| `market_stock_daily` | One equity's OHLCV bar for one trading day, raw and bonus/right-adjusted (`adj_*`) |
| `market_trade` | One executed trade from NEPSE's floor sheet, with buyer/seller broker codes |
| `market_order_book_snapshot` | One security's order book (up to 5 bid/ask levels) at one live scrape |
| `market_sector_snapshot` | One sector's session-to-date turnover/volume/trades at one live scrape |
| `market_security` | One listed, suspended or delisted security (security master) |
| `market_broker` | One NEPSE broker (member) by broker number |
| `market_backfill_state` | Resume cursor of a market-data history backfill |
| `market_index_drawdown` (view) | Log return and drawdown from the running peak per index and day |
| `news_article` | One news article from a Nepali portal |
| `news_backfill_url` / `news_backfill_progress` / `news_backfill_cursor` / `news_backfill_idwalk_cursor` | Work queue, per-day progress and cursors of the historical news backfill |
| `pipeline_run` | One workflow run (status, counts, timing) |
| `app_user` | One dashboard login account |

---

## How to Deploy

```bash
git clone https://github.com/shiksha777-max/Sim-Alpha-Web-Scrapping-
cd Sim-Alpha-Web-Scrapping-
cp .env.example .env
# Fill in DB credentials in .env
docker-compose up --build
```

After startup:
- Dashboard (Nginx): `http://localhost`
- FastAPI direct: `http://localhost:8001`

---

## Local Development (without Docker)

Python dependencies are declared in `pyproject.toml` files, not `requirements.txt`:

- `pyproject.toml` at the repo root lists the dependencies of **every** service
  plus the shared `nepse-common` package (installed editable). It builds one
  development virtualenv; Docker does not use it.
- `nepse-service/`, `news-service/` and `api-service/` each have their own
  `pyproject.toml`, which that service's Dockerfile installs. Keep the pins in
  the service file and the root file the same.

```bash
uv sync                      # creates .venv on Python 3.14 (.python-version)
uv sync --extra scripts      # also Playwright, for scripts/nepsealpha-scraper
source .venv/bin/activate

# without uv
python3.14 -m venv .venv
.venv/bin/pip install -e ./nepse-common -e .
```

Services run from their own directory against the Docker database (whose
port is published on `localhost`), e.g. the API on a spare port:

```bash
cd api-service
POSTGRES_HOST=localhost TEMPORAL_ADDRESS=localhost:7233 uvicorn main:app --reload --port 8002
```

Don't start a worker (`python worker.py`) against the Docker Temporal server
while the containers run: it would pick up the live tasks.

---

## API Endpoints

### GET /articles
```
GET /articles?hours=24&tier=finance&limit=50
```
Returns recently scraped news articles.

### GET /nepse-index
```
GET /nepse-index?hours=24
```
Returns NEPSE main index and sector indices for the last N hours.

### GET /health
Returns `{"status": "ok"}` if running.

### Dashboard APIs
These endpoints power the dashboard UI.

### GET /dashboard/overview
Returns summary metrics, latest NEPSE value, sector snapshot, and top sources.

### GET /dashboard/latest-news
Returns latest scraped news for dashboard cards.

### GET /dashboard/nepse-history
Returns NEPSE time-series points for trend chart.

---

## Data Collection Plan
- Interval: every 30 minutes
- Duration: minimum 2 weeks
- Expected articles: ~400 per run (20 portals x 20 articles)
- Expected total: 20,000 to 30,000 articles over 2 weeks
