# NEPSE Insights

A data platform for research on **market crash detection for NEPSE** (Nepal Stock Exchange).

It collects live NEPSE market data every minute during trading hours, keeps long-history
research datasets for model calibration and backtesting, scrapes Nepali financial and general
news, runs business-intelligence agents and a portfolio optimiser, and shows all of it on a
React dashboard.

---

## What It Does

- **Live market data**: every minute during trading hours, from the official
  nepalstock.com.np API: all 17 index values, every security's price and volume, every
  trade on the floor sheet, order-book depth and per-sector turnover.
- **Research datasets**: daily OHLCV for every index (NEPSE since 2000) and every equity,
  including delisted ones; about one intraday tick per minute for the indices since 2018;
  broker-level trades; company fundamentals and corporate actions (dividends, bonus and
  right issues).
- **News**: 20 Nepali portals scraped every 15 minutes, plus historical backfills
  (sitemaps, cursors, GDELT) for event context.
- **Business intelligence**: technical, fundamental, news and quantitative agents run 24/7
  over the scripts you set up and produce a report, a recommendation and alerts for each.
  A Q&A box answers questions about them, and a portfolio optimiser finds the lowest-risk
  allocation for a budget, horizon and target return.
- **Dashboard**: market history, drawdowns, order book, broker flows, technicals,
  candlestick charts, news, pipeline health and the BI pages.

---

## Architecture

```
nepalstock.com.np ─┐
merolagani.com ────┴──► nepse-service ──┐
                                        ├──► PostgreSQL ◄──── business-intelligence
20 news portals ───┬──► news-service ───┘        ▲            (agents, gRPC :50051)
GDELT ─────────────┘                             │                      ▲
                                                 │                      │ gRPC
                                           api-service :8001 ───────────┘
                                                 ▲
                                                 │ /api/
                                   browser ──► Nginx :80 (React dashboard)

Temporal (:7233, UI :8080) schedules and runs the jobs of the three workers.
```

| Service | Role |
|---|---|
| `db` | PostgreSQL 15 (Asia/Kathmandu time zone) |
| `temporal`, `temporal-ui` | Runs every schedule and workflow; UI on `:8080` |
| `nepse-service` | Temporal worker for all NEPSE market data: live scrapes, end-of-day bars, history backfills, fundamentals |
| `news-service` | Temporal worker for news: live portal scraping and historical backfills |
| `business-intelligence` | BI agents, alert monitor and portfolio optimiser. Reads the database only and serves api-service over gRPC (`127.0.0.1:50051`) |
| `api-service` | FastAPI on `:8001`: reads the database, forwards BI calls over gRPC, handles login |
| `nginx` | Builds and serves the dashboard on `:80` and proxies `/api/` to api-service |

All scheduling is done by Temporal. Each worker registers its schedules on startup, and every
workflow run writes a row to `pipeline_run`, which the dashboard's **Logs** page shows.

---

## Technology

| Technology | Purpose |
|---|---|
| Python 3.14 | All backend services |
| Temporal | Schedules and durable workflows (scraping, backfills, BI automation) |
| PostgreSQL 15 + SQLAlchemy 2.0 + Alembic | Storage, ORM and schema migrations |
| requests, BeautifulSoup4, wasmtime | Scraping; `wasmtime` runs NEPSE's `nepse.wasm` to derive API tokens |
| FastAPI | REST API with Server-Sent Events for streaming BI answers |
| gRPC | api-service ↔ business-intelligence |
| numpy, scipy | Indicators, GARCH, VaR, jump detection, Monte Carlo, portfolio optimisation |
| OpenAI-compatible LLM (optional) | Report summaries, news sentiment, Q&A |
| React, TypeScript, Vite, Tailwind, recharts, KLineChart | Dashboard |
| Nginx, Docker Compose | Serving and deployment |

---

## Getting Started

Requires Docker with Compose.

```bash
git clone https://github.com/tekraj/Nepse-Insights.git
cd Nepse-Insights
cp .env.example .env              # fill in credentials; see "Configuration"
docker compose up -d --build

# Apply the database schema (first run, and after pulling schema changes)
docker compose run --rm --no-deps nepse-service sh -c 'cd /nepse-common && alembic upgrade head'

# Create a dashboard login (there is no sign-up)
docker compose exec api-service python manage.py create-admin
```

After startup:

- Dashboard: <http://localhost>
- API: <http://localhost:8001>
- Temporal UI: <http://localhost:8080>
- PostgreSQL: `localhost:5432`, or `docker exec -it nepse-postgres-db psql -U superset -d nepse`

After changing a service's code, rebuild only that service, for example
`docker compose up -d --build nepse-service`. A change to `nepse-common` needs a rebuild of
every service that uses it.

On first start, nepse-service imports the CSV exports in `nepse-service/historical-data/` and
starts the research and floor-sheet backfills. These run in the background and can take hours
to days, depending on the settings below.

---

## Configuration

All settings come from `.env`. [`.env.example`](.env.example) lists and explains each one.
The ones you are most likely to change:

| Setting | Effect |
|---|---|
| `POSTGRES_*` | Database credentials |
| `JWT_SECRET`, `COOKIE_SECURE` | Login token secret (change it); set `COOKIE_SECURE=true` behind HTTPS |
| `LIVE_NEPSE_SCRAPE_ENABLED` | Turns on the 1-minute live index scrape |
| `SCRAPER_INTERVAL_MINUTES` | News scraping cadence (default 15) |
| `MARKET_DEPTH_TOP_N`, `MARKET_DEPTH_BATCH_SIZE` | How many of the most liquid stocks get order-book snapshots, and how many per minute |
| `RESEARCH_BACKFILL_ENABLED`, `INTRADAY_BACKFILL_START_DATE`, `INTRADAY_BACKFILL_STOCKS` | Depth of the research backfill; `INTRADAY_BACKFILL_STOCKS=ALL` adds intraday ticks for every equity (~20M rows) |
| `FLOORSHEET_BACKFILL_START_DATE` | How far back past floor sheets are completed with broker codes (merolagani has data from ~2020) |
| `HISTORICAL_NEWS_BACKFILL_ENABLED` | Historical news crawl (off by default) |
| `BI_LLM_MODEL`, `BI_LLM_API_KEY`, `BI_LLM_BASE_URL` | Optional LLM for the BI agents (see below) |
| `BI_AUTOMATION_ENABLED` | `false` pauses the BI report and alert schedules |

---

## Data Collection

All times are Nepal time (NPT).

| What | When | Table |
|---|---|---|
| Index values (17 indices) | every minute in market hours | `market_index_snapshot` |
| Every security's price/volume | every minute in market hours | `market_price_snapshot` |
| Floor sheet (latest trades) | every minute in market hours | `market_trade` |
| Sector turnover | every minute in market hours | `market_sector_snapshot` |
| Order-book depth | every minute in market hours (rotating through the most liquid stocks) | `market_order_book_snapshot` |
| Full floor sheet with broker codes | 15:20 and 17:00 on session days | `market_trade` |
| Official daily bars + today's ticks | 15:40 on session days | `market_index_daily`, `market_stock_daily`, `market_intraday_tick` |
| Company fundamentals and corporate actions | 16:15 on session days | `market_fundamental_daily`, `market_corporate_action` |
| Deep daily and intraday history | Saturday 06:00 and on startup | `market_index_daily`, `market_stock_daily`, `market_intraday_tick`, `market_security` |
| Past floor sheets (broker codes, missed trades) | Sunday 06:00 (last 30 days) and on startup (back to `FLOORSHEET_BACKFILL_START_DATE`) | `market_trade` |
| News from 20 portals | every 15 minutes | `news_article` |

"Market hours" means NEPSE itself reports the market as open, so holidays are skipped
automatically.

### News portals (20)

- **Finance and NEPSE focused**: Merolagani, Sharesansar, Nepsealpha, NepseKhabar,
  Nepali Paisa, Karobar Daily, Arthik Abhiyan, Biznews Nepal, Stock Nepali, NEPSE Trading
- **General news (politics, economy, policy)**: Onlinekhabar, Setopati, Ratopati,
  Ekantipur, Nagarik News, The Himalayan Times, MyRepublica, Republica, Annapurna Post,
  Nepal Live

### Indices (17)

NEPSE, Sensitive, Float, Sensitive Float, and the 13 sector sub-indices (Banking, Development
Bank, Finance, Hotels & Tourism, Hydropower, Investment, Life Insurance, Manufacturing &
Processing, Microfinance, Mutual Fund, Non-Life Insurance, Others, Trading). The registry is
in [`nepse-common/nepse_common/constants/index_registry.py`](nepse-common/nepse_common/constants/index_registry.py).

### Notes for using the data

- **Timestamps are naive Nepal time** (UTC+5:45, no DST).
- **NEPSE's trading week changed.** Sessions ran Sunday to Thursday until 2026-04-05 and run
  Monday to Friday from 2026-04-06 (with 15 extra Friday sessions between 2022-05-20 and
  2022-09-16). Take the trading calendar from `market_index_daily` rows where
  `index_name = 'NEPSE'`, never from a weekday rule.
- **Use the `adj_*` columns of `market_stock_daily` for returns.** Raw prices drop sharply
  on bonus and right ex-dates.
- **`market_intraday_tick` holds point observations, not bars.** Resample before computing
  returns. Equity tick prices are raw NPR.
- **Crash labels**: `market_index_drawdown` (a view) gives drawdowns per index and day, and
  `manage_data.py crash-events` turns them into drawdown episodes at a threshold you choose.

---

## Database Tables

Table names start with the subsystem that owns them (`market_`, `news_`,
`pipeline_`, `app_`, `bi_`); market tables end with their granularity (`_snapshot` =
one row per live scrape, `_daily` = one row per trading day, `_tick` = point
observations). Every table carries a description: run `\dt+` / `\d+ <table>`
in psql. All timestamps are naive Nepal time (NPT). Schema changes go through
Alembic revisions in `nepse-common/alembic/versions/`.

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
| `market_fundamental_daily` | One equity's fundamentals (EPS, P/E, book value, P/BV, dividend, market cap) for one trading day (merolagani) |
| `market_corporate_action` | One cash dividend / bonus / right issue of an equity for a Nepali fiscal year |
| `market_backfill_state` | Resume cursor of a market-data history backfill |
| `market_index_drawdown` (view) | Log return and drawdown from the running peak per index and day |
| `news_article` | One news article from a Nepali portal |
| `news_backfill_url` / `news_backfill_progress` / `news_backfill_cursor` / `news_backfill_idwalk_cursor` | Work queue, per-day progress and cursors of the historical news backfill |
| `bi_setting` | One script's business-intelligence setup (analyses, indicator parameters, refresh, alerts) |
| `bi_report` | One script's current BI report (agents' findings + recommendation), overwritten on each refresh |
| `bi_notification` | One BI alert (price move, volume spike, news, recommendation change) |
| `bi_portfolio` | One user's latest portfolio optimisation (request + result) |
| `pipeline_run` | One workflow run (status, counts, timing) |
| `app_user` | One dashboard login account |

---

## Dashboard

Every page except `/login` requires signing in.

| Page | Shows |
|---|---|
| `/` | Overview: latest NEPSE value, sectors, latest news |
| `/market` | Official daily index history, drawdown episodes, volatility, turnover, intraday path |
| `/orderbook` | Market depth for the most liquid stocks |
| `/brokers` | Floor-sheet broker flows, concentration, trade sizes, dataset coverage |
| `/technicals` | Indicators for any index or stock (stocks use bonus/right-adjusted prices by default) |
| `/candles` | Candlestick charts at 1H/1D/1W/1M with MA/EMA/BOLL/VOL/MACD/RSI and drawing tools |
| `/news`, `/news/:id` | Scraped articles |
| `/logs` | Health of every pipeline job, including the longest gap between runs |
| `/bi` | A script's BI report and Q&A |
| `/portfolio` | Portfolio optimiser |
| `/admin/bi` | BI Setup |

---

## Business Intelligence & Portfolio Optimiser

The `business-intelligence` service runs four specialist agents (technical, fundamental,
news, quantitative) and a master agent 24/7 over the scripts set up on the dashboard's
**BI Setup** page, and serves api-service over gRPC:

- **BI Setup** (`/admin/bi`): pick scripts and, per script, the indicators/metrics and
  parameters (e.g. MACD + RSI for NABIL, candlesticks for HBL), refresh cadence and alerts.
- **BI** (`/bi`): each script's report (recommendation, buy/sell view, technical charts,
  fundamentals, news sentiment, risk statistics) and a Q&A box that answers from the report
  plus live database lookups, streamed over Server-Sent Events.
- **Portfolio** (`/portfolio`): budget + horizon + target return → the lowest-risk
  combination of scripts expected to reach it, as share orders, with a risk analysis
  (probability of reaching the target, VaR/CVaR, drawdown, stress, frontier). Progress
  streams over SSE; the last result is kept per user.
- **🔔 alerts**: price moves, volume spikes, new news and recommendation changes.

Reports refresh every 5 minutes when they are due, and the alert monitor runs every minute.
The agents only compute from the database; company fundamentals are scraped by
nepse-service (daily after the close). An LLM is optional: set `BI_LLM_MODEL` with
`BI_LLM_API_KEY` (OpenAI) or `BI_LLM_BASE_URL` (any OpenAI-compatible server, such as
Ollama or OpenRouter) in `.env`; without one, summaries are rule-based and Q&A is off.
Q&A needs a model that supports tool calling.

---

## API Endpoints

The dashboard reaches the API through Nginx at `/api/...`; the API itself listens on `:8001`.
Login sets an httponly cookie (`nepse_access_token`); a bearer token also works.

| Endpoints | Auth | Purpose |
|---|---|---|
| `GET /health` | public | `{"status": "ok"}` |
| `GET /articles?hours=24&tier=finance&limit=50` | public | Recently scraped news articles |
| `GET /nepse-index?hours=24` | public | Index values for the last N hours |
| `POST /auth/signin`, `POST /auth/logout`, `GET /auth/me` | — | Login session |
| `GET /dashboard/...` | required | Data behind the dashboard pages: `overview`, `latest-news`, `nepse-history`, `sector-history`, `news`, `pipeline-logs`, `pipeline-health`, `indicators`, `stocks`, `stock-indicators`, `candles`, `indices`, `market/*`, `floorsheet/*` |
| `POST /admin/historical/backfill`, `GET /admin/historical/backfill/status` | required | Start and track the historical news backfill |
| `GET /admin/bi/catalog`, `GET/PUT/DELETE /admin/bi/settings/{symbol}` | required | BI Setup |
| `GET /bi/reports[/{symbol}]`, `POST /bi/reports/{symbol}/refresh` | required | BI reports |
| `POST /bi/ask` | required | Q&A (Server-Sent Events) |
| `POST /bi/portfolio/optimize`, `GET /bi/portfolio` | required | Portfolio optimiser (Server-Sent Events) and the last result |
| `GET /bi/notifications`, `POST /bi/notifications/read` | required | Alerts |

---

## Data Management

```bash
# Coverage of every dataset
docker compose exec nepse-service python manage_data.py coverage

# Quarantine rows scraped on non-trading days (dry run unless --apply)
docker compose exec nepse-service python manage_data.py cleanup-stale [--apply]

# Drawdown episodes (crash labels) for an index at a threshold
docker compose exec nepse-service python manage_data.py crash-events --index NEPSE --threshold 0.2 [--csv]
```

To re-run a missed job (for example the evening floor-sheet sweep), start its workflow from
the Temporal UI on the worker's task queue (`nepse-market-queue`, `news-scraper-queue` or
`bi-automation-queue`).

---

## Local Development (without Docker)

Python dependencies are declared in `pyproject.toml` files, not `requirements.txt`:

- `pyproject.toml` at the repo root lists the dependencies of **every** service
  plus the shared `nepse-common` package (installed editable). It builds one
  development virtualenv; Docker does not use it.
- `nepse-service/`, `news-service/`, `api-service/` and `business-intelligence/` each
  have their own `pyproject.toml`, which that service's Dockerfile installs. Keep the
  pins in the service file and the root file the same.

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
while the containers run: it would pick up the live tasks and re-register the schedules.
To try an activity against the real API and database, run it once with
`temporalio.testing.ActivityEnvironment` (see `CLAUDE.md`, "Testing changes").

The dashboard runs on its own with a dev server:

```bash
cd dashboard && pnpm install && pnpm dev     # http://localhost:5173
```

After editing the gRPC contract (`nepse-common/nepse_common/bi_grpc/business_intelligence.proto`),
regenerate the stubs with `scripts/generate_bi_grpc.sh` from the activated venv.

There is no automated test suite.

---

## Repository Layout

```
nepse-common/           shared package: config, SQLAlchemy models, upserts, gRPC contract, Alembic migrations
nepse-service/          NEPSE market-data worker (scrapers, activities, workflows, schedules, manage_data.py)
news-service/           news worker (portal scrapers, historical backfills)
business-intelligence/  BI agents, analytics, alert monitor, portfolio optimiser, gRPC server
api-service/            FastAPI backend (routers, services, manage.py create-admin)
dashboard/              React + TypeScript dashboard (dist/ is committed build output)
nginx/                  builds and serves the dashboard, proxies /api/
scripts/                one-off tools (index CSV downloaders, news export, gRPC stub generator)
data/                   Postgres data dir, index CSV exports, exported article text
docker-compose.yml      the full stack
.env.example            settings template
CLAUDE.md               detailed developer notes (schedules, tables, source quirks)
```
