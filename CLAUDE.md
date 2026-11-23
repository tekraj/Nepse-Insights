# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A data platform for a Kathmandu University data-science thesis on **market crash detection for NEPSE** (Nepal Stock Exchange) — see `thesis/main.tex` (TDA on correlation networks + Mean Field Games + jump-diffusion/COGARCH). It:

- collects live NEPSE market data every minute during trading hours (index values, every stock's price, every trade, order-book depth, sector turnover) from the official nepalstock.com.np API;
- maintains long-history **research datasets** (daily OHLCV for every index and equity back to 2000/2010, ~1-minute index ticks back to 2018, broker-level trades) for model calibration and backtesting;
- scrapes ~20 Nepali news portals (plus historical backfills) for event context;
- exposes everything through a FastAPI backend and a React dashboard behind Nginx.

The README describes an older idealized layout (`nepali-news-pipeline/`, a single `nepse-news-scraper/` monolith). Both are gone — trust this file and the directory layout over the README.

## Repository Layout

- `nepse-common/` — shared Python package installed editable into every service image and the dev venv (`pip install -e`): `config.py` (all settings from env vars), `models/` (SQLAlchemy 2.0 ORM), `db/session.py` (cached engine + `session_scope`), `db/upserts.py` (idempotent bulk upserts for the research tables), `constants/index_registry.py` (the 17 NEPSE indices with their official id, canonical name and merolagani symbol), `schemas/`, and **`alembic/`** (the only place schema changes live).
- `nepse-service/` — Temporal worker for all NEPSE market data. `scraper/` = HTTP clients (`nepse_wasm_auth.py` official-API token derivation, `nepse_market_data.py` official endpoints, `nepse_scraper.py` live index with fallbacks, `merolagani_history.py` deep history, `historical_nepse_loader.py` CSV parser), `activities/`, `workflows/`, `register_schedules.py`, `worker.py`, `manage_data.py` (coverage report + stale-data cleanup CLI), `historical-data/` (CSV exports imported on startup).
- `news-service/` — Temporal worker for news: live portal scraping (`scraper/scrapers.py`) and historical backfills (sitemap / cursor / sequential-id discovery, GDELT daily, article-field repair).
- `api-service/` — FastAPI (`main.py`, `routers/`, `services/`, `manage.py create-admin`). Reads the DB; starts the news historical backfill workflow via Temporal (`/admin/historical/backfill`).
- `dashboard/` — React + TypeScript + Vite + Tailwind (recharts). Routes `/login`, `/`, `/market` (official daily index history, drawdown episodes, volatility, turnover, intraday path), `/orderbook` (market depth), `/brokers` (floor-sheet broker flows, concentration, trade sizes, dataset coverage), `/technicals` (indicators for any index or stock — `components/SecurityPicker.tsx` searches both; selection in the URL as `?index=` / `?stock=`; stocks default to bonus/right-adjusted prices), `/candles` (KLineChart 9.8 candlesticks at 1H/1D/1W/1M for positional trading, MA/EMA/BOLL/VOL/MACD/RSI, drawing tools; drawings live in the viewer's localStorage per symbol+timeframe, horizontal lines per symbol), `/news`, `/news/:id`, `/logs` (per-job pipeline health incl. longest gap between runs); all but `/login` behind `ProtectedRoute`. Shared bits: `lib/useApi.ts` (fetch + 401 redirect), `lib/format.ts` (`parseNpt` — the API's timestamps are naive NPT, so never `new Date()` them directly), `components/NavLinks.tsx`. `dist/` is committed build output — don't hand-edit it.
- `nginx/` — builds the dashboard (pnpm) and serves it; proxies `/api/` to `api-service:8001`.
- `scripts/` — one-off tools: `nepsealpha-scraper/` (sharesansar/nepsealpha index CSV downloaders + `seed_from_csv.py`), `export_nepse_news_to_files.py`.
- `data/` — `pgsql/` (Postgres bind-mounted data dir, root-owned), `sector-2021-2026/` (index CSV exports), `nepse_news/` (exported article text files).
- `thesis/` — the LaTeX research proposal the datasets exist for.
- `init.sql` / `init2.sql` — old SQL dumps; `init.sql` is mounted into Postgres's `docker-entrypoint-initdb.d` (only runs on an empty data dir).
- `test.py` — scratch script for probing the NEPSE API; not a test suite.
- `pyproject.toml` (root) — the **development venv**, not used by Docker: every service's dependencies + nepse-common (editable, via `[tool.uv.sources]`) + a `scripts` extra (Playwright). `uv sync` creates `.venv` on Python 3.14 (`.python-version`, same as the `python:3.14-slim` images; uv downloads 3.14 if the host lacks it). It ships no code (`packages = []`, uv `package = false`).
- `<service>/pyproject.toml` — what each image installs (dependencies only, `packages = []`; the code runs from its directory). Its Dockerfile `pip install`s nepse-common, then this file, then copies the code. The root file repeats these pins, so **a dependency change goes into both**. There are no `requirements.txt` files any more.

There is no automated test suite. Verify changes by running activities against the live API/DB (see "Testing changes") and checking `manage_data.py coverage` / `pipeline_run`.

## Architecture

**Services** (`docker-compose.yml`): `db` (Postgres 15, container `nepse-postgres-db`, TZ Asia/Kathmandu; `mem_limit` 8g and memory/SSD/parallelism settings as `-c` flags in its `command:` — they override `postgresql.conf` in the data volume, so tune there; `shm_size` 4g, as Docker's 64 MB default made parallel VACUUM/queries fail), `temporal` + `temporal-ui` (:8080), `nepse-service`, `news-service`, `api-service` (:8001), `nginx` (:80).

**Temporal does all scheduling.** Each worker's `register_schedules.py` upserts its schedules on startup (idempotent create-or-update); workflows are thin orchestration, activities do the I/O. Task queues: `nepse-market-queue` (nepse-service), `news-scraper-queue` (news-service). Every workflow run writes one `pipeline_run` row (`source` identifies the job) — the dashboard's Logs page reads it, and it's the first place to look when a dataset stops growing.

**NEPSE's trading week has changed — never hard-code it.** Sessions were **Sunday–Thursday** until **2026-04-05** (last Sunday session) and are **Monday–Friday** from **2026-04-06** (first Friday session 2026-04-10). In between there was a temporary period, **2022-05-20 .. 2022-09-16**, with 15 extra Friday sessions while Sundays continued. Saturday has never been a session. Consequences:
- For any historical analysis, take the trading calendar from `market_index_daily` (`index_name = 'NEPSE'`), never from a weekday rule; day-of-week features/effects must account for the regime change (a "Sunday" session pre-2026 is the first session of the week, like a Monday now).
- Live code asks NEPSE's market status instead of trusting a weekday list (`is_market_open_activity`; Mon–Fri is only its fallback), and post-close jobs run Sun–Fri, skipping themselves when there was no session.

**nepse-service schedules** (all times NPT):

| Schedule | When | Workflow → table |
|---|---|---|
| index | every `NEPSE_SCRAPER_INTERVAL_MINUTES` (1), market hours, needs `LIVE_NEPSE_SCRAPE_ENABLED=true` | `NepseIndexScrapeWorkflow` → `market_index_snapshot` (all 17 indices; official API, nepsetrading/merolagani fallback) |
| today-price | every minute, market hours | → `market_price_snapshot` |
| floor sheet | every minute, market hours | → `market_trade` (latest 500 contracts) |
| sector summary | every minute, market hours | → `market_sector_snapshot` |
| market depth | every minute, market hours | → `market_order_book_snapshot` (`MARKET_DEPTH_BATCH_SIZE` of the `MARKET_DEPTH_TOP_N` most liquid stocks per tick) |
| floor-sheet EOD sweep | Sun–Fri 15:20 and 17:00 (skips days without a session) | `NepseFloorSheetEodSweepWorkflow` → completes the day's `market_trade` + fills broker codes |
| end of day | Sun–Fri 15:40 (skips days without a session) | `NepseEndOfDayWorkflow` → official daily bars into `market_stock_daily` / `market_index_daily`, today's ticks into `market_intraday_tick` |
| research backfill | Saturday 06:00, plus once on every worker startup | `ResearchHistoryBackfillWorkflow` → `market_security`, `market_index_daily`, `market_stock_daily`, `market_intraday_tick` |
| floor-sheet history | worker startup: `FLOORSHEET_BACKFILL_START_DATE` .. yesterday (the deep walk; resumes after restarts); Sunday 06:00: last 30 days only | `FloorSheetHistoryBackfillWorkflow` → completes past `market_trade` sessions (broker codes + missed trades) from merolagani; continue-as-new every 100 sessions |
| CSV import | once on startup | `HistoricalNepseCsvImportWorkflow` → `market_index_snapshot` + `market_index_daily` (idempotent via a `pipeline_run` success row with message `historical_nepse_csv_import_v2`) |

"Market hours" = `is_market_open_activity`: any day but Saturday, 10:55–15:05 NPT, **and** NEPSE's own `/api/nots/nepse-data/market-open` status says OPEN (so holidays and non-session weekdays are skipped). During the post-close padding it also requires that today's session was actually seen; if the status call fails, the last status read in the past 10 minutes decides, and only with none does it degrade to a Mon–Fri clock gate (the bare clock gate leaked stale index/depth rows onto the 2026-10-19..23 Dashain holidays). Writers additionally drop rows whose `businessDate` isn't today.

Calendar schedules are written in UTC via `_npt_calendar()` (NPT is fixed UTC+5:45, no DST) rather than `time_zone_name`. Interval schedules use `_npt_aligned_offset()` so grids land on NPT wall-clock boundaries, plus a per-schedule seconds offset (`_every()`: index :05, today-price :09, floor sheet :13, sector :17, depth :21) — never fire nepalstock scrapes at :00 (see the gotchas below). (news-service's `HISTORICAL_DAILY_HOUR_NPT` calendar is *not* converted, so it actually fires at that hour UTC.)

**Data flow to the frontend:** dashboard → `/api/...` → Nginx → `api-service` → Postgres. The API (`services/nepse_service.py`, `market_service.py`, `floorsheet_service.py`, `stock_service.py`, `candle_service.py`, `pipeline_log_service.py`) reads `market_index_snapshot` (live ticks), `market_index_daily` + `market_index_drawdown` (anything longer than a week, technicals), `market_intraday_tick`, `market_stock_daily` + `market_security` (stock search and per-stock technicals; both share `nepse_service.indicator_points`), `/dashboard/candles` (OHLCV at 1m..1M: ticks bucketed from `market_intraday_tick`, sessions it lacks — today, stocks not yet backfilled — from the 1-minute `market_index_snapshot` / `market_price_snapshot` scrapes since 2026-09-15, daily+ from the daily tables with a provisional bar for today; drops the index's post-15:00 tick that carries the day's whole turnover at the pre-close value), `market_order_book_snapshot`, `market_price_snapshot`, `market_trade`, `news_article` and `pipeline_run`. API response keys predate the 2026-11 table/column rename and were kept (e.g. `ltp`, `total_buy_qty`, `nepse_source`), so the dashboard didn't change. Trade aggregates go through `trade_date` (indexed) and the coverage endpoint's full scan (~5 s) is cached for 10 min.

**Auth:** api-service issues HS256 JWTs (`JWT_SECRET`, `JWT_TTL_MINUTES`) as an httponly cookie `nepse_access_token` or bearer token. Accounts live in `app_user` (no signup; `docker compose exec api-service python manage.py create-admin`). `/dashboard/*` and `/admin/*` require auth; `/articles`, `/nepse-index`, `/health` are public.

## Database

All timestamps are **naive NPT** (`scraped_at` defaults come from the DB's `now()` in Asia/Kathmandu). Schema changes go through a new Alembic revision in `nepse-common/alembic/versions/` plus the matching model — never ad-hoc DDL. Every table and its non-obvious columns carry a `COMMENT` (`\dt+`, `\d+ <table>` in psql); keep the model's `comment=` and the migration in sync.

**Naming** (revision 0013 renamed everything to this; the old `nepse_*` / `historical_*` / `research_*` names are gone): snake_case, singular table names, prefixed by the owning subsystem — `market_` (NEPSE data), `news_` (articles + news-backfill bookkeeping), `pipeline_`, `app_`. Market table suffix = granularity: `_snapshot` one row per live scrape (plain-insert timeseries), `_daily` one row per trading day, `_tick` point observations, none = master/per-event table. One name per concept across tables: `trade_date` (session date), `volume` (shares), `turnover` (NPR), `trade_count`, `security_id` (NEPSE's id, = `market_security`), `broker_code` (broker number, = `market_broker`), `open/high/low/close`; no abbreviations (`last_traded_price`, not `ltp`). ORM classes mirror table names (`market_trade` → `MarketTrade`). Temporal activity payload keys and API response keys were deliberately left as they were.

### Live market data (nepalstock.com.np, since 2026-09-15 unless noted)
- `market_index_snapshot` — one row per index per scrape: `index_value`, `point_change`, `percent_change`. Mixed granularity: one 15:00 close per trading day from the CSV import (2021-01-17 → 2026-06-29), irregular ticks 2026-06-29 → 09-14, 1-minute after. Dashboard source; for research use `market_index_daily` / `market_intraday_tick`.
- `market_price_snapshot` — every traded security's session-to-date stats each minute (`last_traded_price`, `open/high/low` so far, `volume`, `turnover`, `trade_count`, `average_traded_price`, `last_traded_at` = time of the security's last trade). `close` is always NULL intraday (NEPSE sets it only after the close). `last_traded_price`/`volume` are NULL before 2026-09-23.
- `market_trade` — the floor sheet: every trade (`contract_id` unique per `trade_date`, `trade_time` to the microsecond, `quantity`, `price`, `amount`, `buyer/seller_broker_code` + broker names, `security_id`). NEPSE serves broker fields only **after 15:00**, so intraday rows have them NULL until the EOD sweep upserts them (`ON CONFLICT` fills NULL columns only). Past sessions (NEPSE can't serve them) are completed from merolagani's floor-sheet history by `FloorSheetHistoryBackfillWorkflow`: broker codes for every trade, broker names from `market_broker`, and the missing trades — which have `trade_time` NULL and no `security_id`/`trade_book_id` (merolagani doesn't publish them). Names on backfilled sessions are each broker code's **current** official name (a firm that renamed shows its new name for 2020 too); names NEPSE published with the trades (live sweeps) are never overwritten. Sessions completed before the broker master existed were filled once with `manage_data.py fill-broker-names`. Rows without a broker code (merolagani lists equities only, so mutual-fund/debenture trades in backfilled sessions) have no name either.
- `market_order_book_snapshot` — order-book (market depth) snapshots (`buy_levels`/`sell_levels` JSONB, ≤5 levels each; `total_buy_quantity`/`total_sell_quantity`).
- `market_sector_snapshot` — per-sector session-to-date `turnover`/`volume`/`trade_count`/`traded_security_count` per minute (empty before 2026-10-15: the endpoint is GET-only and was being POSTed).
- `trade_date` in these three tables is TEXT `'YYYY-MM-DD'` (NEPSE's `businessDate`), unlike the DATE `trade_date` of the daily tables — compare with strings or cast. Converting it means rewriting the 17 GB `market_trade`; not done yet.

### Research datasets (built by the research/EOD workflows)
- `market_index_daily` (PK `index_name, trade_date`) — daily OHLC + turnover for all 17 indices. NEPSE from 2000-01-03, most sub-indices from 2014–2016. Its NEPSE rows are the **trading calendar**. `volume`/`trade_count` exist only for official rows (last ~1 year).
- `market_stock_daily` (PK `symbol, trade_date`) — every equity incl. delisted (~490). Raw `open..close, volume` plus `adj_*` (bonus/right-adjusted; use these for returns — raw prices have huge ex-date drops). `adj_*` are refreshed weekly (factors change retroactively) and are NULL for rows added since the last refresh.
- `market_intraday_tick` (PK `symbol, tick_time`, `instrument_type` index/equity) — `price` + `volume` point observations from 2018-03-29 (merolagani's limit). Indices ~1 per minute. Equities per `INTRADAY_BACKFILL_STOCKS` (`ALL` = every active equity plus those delisted since `INTRADAY_BACKFILL_START_DATE`, ~345, so the 2021–23 mergers don't add survivorship bias): ~15–90 prints per session, `volume` = shares in that print (sums to ≤ the day's volume), `price` in **raw NPR** — each session is rescaled from merolagani's adjusted values so its last tick equals the official close (see gotchas); multiply by that day's `adj_close / close` from `market_stock_daily` for cross-day returns. A few equity ticks sit up to ~2% below the daily low (likely odd-lot trades). Not bars and not minute-aligned — resample before computing returns.
- `market_security` — security master (`security_name` = the instrument, `company_name` = issuer, sector, instrument type, `listing_status` A/S/D).
- `market_backfill_state` (PK `dataset, item_key`) — resume cursors: `intraday` per symbol (covered window), `daily_full_refresh` (`*`, last run), `floorsheet_history` per session date (completed from merolagani).
- `market_index_drawdown` (view) — per index/day: `log_return`, `running_peak`, `drawdown` over `market_index_daily`. `manage_data.py crash-events` turns it into drawdown episodes (crash ground truth); the crash threshold is a modelling choice, not stored.

Source precedence for the daily tables (`db/upserts.py`): `nepalstock` (official) > `merolagani` > `csv`. A lower-ranked source never overwrites a higher one; `adj_*` always come from merolagani.

### Other
`market_broker` (PK `broker_code` = `market_trade.buyer/seller_broker_code` → current official `broker_name`, `active_status` A/SUSPEND, `is_dealer`, `nepse_internal_id` = NEPSE's own row id, *not* the broker number; from NEPSE's member list, refreshed when older than 7 days by the floor-sheet history backfill — 92 brokers, code 501 seen on 2022-11-13 isn't one), `news_article` (deduped by `url`, `source` = portal, `portal_tier` finance/general), `news_backfill_url` / `news_backfill_progress` / `news_backfill_cursor` / `news_backfill_idwalk_cursor` (historical news backfill queue, per-day progress and cursors), `pipeline_run` (one row per workflow run: `source`, `records_written`, `articles_found`/`articles_inserted`), `app_user`.

## External sources — gotchas

**nepalstock.com.np official API** (`scraper/nepse_wasm_auth.py`): every call needs `Authorization: Salter <token>`, derived per request from `/api/authenticate/prove` salts through the bundled `nepse.wasm`; many POST endpoints also need a numeric payload `id` (`build_payload_id`). TLS chain is incomplete → `verify=False` (only for this host). Send every request through `nepse_request()`, which retries dropped connections: the server closes connections (`RemoteDisconnected`) in bursts, mostly in the first seconds of each minute when every client polls — with all our scrapes at :00 and no retry, 2026-11-04 lost 172 of ~250 market-depth ticks and ~95% of official index ticks (which then fell back to nepsetrading's 12 indices). Verified behaviours:
- History is shallow: `/api/nots/index/history/{id}` and `/api/nots/market/history/security/{id}` keep ~1 year; `today-price?businessDate=` only accepts the last few days ("Searched Date is not valid."). The floor sheet is the **latest session only** (`businessDate` ignored) — past sessions come from merolagani instead.
- `/api/nots/member` (broker list, `fetch_broker_list`) is a POST whose body is a search filter (empty fields = all members), not the usual `{"id": payload_id}`.
- `/api/nots/sectorwise` is GET-only. `/api/nots/nepse-index` gives the 4 headline indices, `/api/nots` the 13 sub-indices.
- Floor sheet pages via `page`/`size=500`; `sort=contractId,desc` orders by segment (contract-id digits 9–10) then sequence, not by time, and pages shift while the market is open — full sweeps are exact only after the close.
- On holidays every endpoint keeps serving the previous session; always check `businessDate`.

**merolagani.com Floorsheet.aspx** (`scraper/merolagani_floorsheet.py`): ASP.NET WebForms — search a date by postback (`txtFloorsheetDateFilter`, MM/DD/YYYY), then 500-row pages via the pager's `hdnCurrentPage` (any page can be jumped to); every postback must carry the previous response's `__VIEWSTATE`. History back to ~2020; contract ids match NEPSE's; no trade time or broker names. Slow for old dates (~1 s/page for 2026, ~7 s for 2025, 10–30 s for 2020–2023) and an overloaded query comes back as a page **without the table** — `page()` raises `FloorSheetPageError` unless it got exactly the requested page, the activity retries with backoff on a fresh session, and a day is marked done only when every page arrived. Sequence check for completeness: per session, `count(*) / sum over segments of max(contract_id % 1e6)` is ≥ 0.998 on complete days.

**merolagani.com chart handler** (`scraper/merolagani_history.py`, `TechnicalChartHandler.ashx?type=get_advanced_chart`): no auth. Symbols are tickers or the index labels in `index_registry.py`. Daily `t` falls on the bar's **UTC** date (not midnight-aligned). Intraday responses look like OHLC but `o==h==l==c` with second-resolution `t` — they are ticks; any requested range comes back as whole sessions (the range is date-granular, UTC dates). Indices' `v` is NPR turnover, equities' `v` is raw shares. Past equity intraday prices are bonus/right-adjusted on a basis that matches neither the raw prices nor the daily `adj_*` series (NABIL 2021-08-08: tick 1065.01, raw close 1494, daily adj 898.74) and shifts with every new corporate action — `_ticks_to_raw_prices` (research_data_activities.py) rescales each session to raw by close / last tick before storing. Pace requests (`MEROLAGANI_REQUEST_PAUSE_SECONDS`).

## Configuration

Everything flows through `nepse_common/config.py: load_app_config()` from `.env` (template: `.env.example`, keep both in sync when adding settings). nepse-service knobs: `NEPSE_SCRAPER_INTERVAL_MINUTES`, `LIVE_NEPSE_SCRAPE_ENABLED`, `SCRAPER_REQUEST_TIMEOUT`, `MARKET_DEPTH_TOP_N`, `MARKET_DEPTH_BATCH_SIZE`, `RESEARCH_BACKFILL_ENABLED`, `RESEARCH_BACKFILL_ON_STARTUP`, `INTRADAY_BACKFILL_START_DATE`, `INTRADAY_BACKFILL_INDICES`, `INTRADAY_BACKFILL_STOCKS` (`""`/`ALL`/comma list), `MEROLAGANI_REQUEST_PAUSE_SECONDS`, `FLOORSHEET_BACKFILL_START_DATE`, `HISTORICAL_NEPSE_CSV_IMPORT_ON_STARTUP`, `HISTORICAL_NEPSE_CSV_DIR`. news-service: `SCRAPER_INTERVAL_MINUTES`, `HISTORICAL_DAILY_*`, `HISTORICAL_NEWS_BACKFILL_ENABLED`, `NEPSE_NEWS_FIELDS_BACKFILL_ENABLED`, etc. Auth: `JWT_SECRET`, `JWT_TTL_MINUTES`, `COOKIE_SECURE`. Temporal: `TEMPORAL_ADDRESS`.

## Commands

```bash
# Full stack
cp .env.example .env            # first time; fill in credentials
docker compose up -d --build    # dashboard http://localhost, API :8001, Temporal UI :8080

# Rebuild/restart one service after code changes (nepse-common changes need a rebuild of every service using it)
docker compose up -d --build nepse-service

# Migrations (run after pulling schema changes; additive ones are safe while workers run)
docker compose run --rm --no-deps nepse-service sh -c 'cd /nepse-common && alembic upgrade head'
docker compose run --rm --no-deps nepse-service sh -c 'cd /nepse-common && alembic revision -m "..."'

# Dataset coverage report / quarantine rows scraped on non-trading days (dry run unless --apply) / crash labels
docker compose exec nepse-service python manage_data.py coverage
docker compose exec nepse-service python manage_data.py cleanup-stale [--apply]
docker compose exec nepse-service python manage_data.py crash-events --index NEPSE --threshold 0.2 [--csv]
docker compose exec nepse-service python manage_data.py fill-broker-names [--apply]   # NULL market_trade broker names from market_broker; resumable

# Admin account for the dashboard
docker compose exec api-service python manage.py create-admin

# psql
docker exec -it nepse-postgres-db psql -U superset -d nepse

# Dashboard dev
cd dashboard && pnpm install && pnpm dev    # :5173 (build: pnpm build)

# Python dev venv without Docker (root pyproject.toml; see "Testing changes")
uv sync                                     # .venv, Python 3.14; add --extra scripts for Playwright
source .venv/bin/activate                   # no uv: python3.14 -m venv .venv && .venv/bin/pip install -e ./nepse-common -e .
```

Trigger a workflow by hand (e.g. after a missed evening) from the Temporal UI (:8080) or a one-off client, e.g. start `NepseFloorSheetEodSweepWorkflow` on task queue `nepse-market-queue` — it must run before the next session opens.

## Testing changes

There are no unit tests. To exercise an activity against the real API/DB without disturbing the running worker, build the image and run it in a one-off container with `temporalio.testing.ActivityEnvironment`:

```bash
docker compose build nepse-service
docker compose run --rm --no-deps -v $PWD/my_check.py:/tmp/check.py:ro nepse-service python /tmp/check.py
# my_check.py: sys.path.insert(0, "/app"); await ActivityEnvironment().run(some_activity, *args)
```

The same check runs from the dev venv without building an image. `.env` is found by `nepse_common/config.py` (it points at the compose hostnames), so override the hosts for the ports compose publishes; the service code is imported from its directory:

```bash
source .venv/bin/activate     # use the activated venv: Python 3.14 warns when run as ../.venv/bin/python
cd nepse-service
POSTGRES_HOST=localhost TEMPORAL_ADDRESS=localhost:7233 python my_check.py
# my_check.py: sys.path.insert(0, "."); await ActivityEnvironment().run(some_activity, *args)
# (paths default to the image's, e.g. HISTORICAL_NEPSE_CSV_DIR=/app/historical-data -- override when needed)
```

Don't start `worker.py` from the venv against the compose Temporal: it would join the production task queue (taking live tasks with your local code) and re-register the schedules. A local api-service is safe: `cd api-service && POSTGRES_HOST=localhost TEMPORAL_ADDRESS=localhost:7233 uvicorn main:app --reload --port 8002` (venv activated).

Avoid running the 1-minute timeseries writers either way during market hours (they'd insert duplicate snapshots next to the live worker's); the upsert-based writers (floor sheet, research tables) are safe to re-run.

## Conventions

- Activities are `async def`; wrap blocking `requests` calls in `asyncio.to_thread`. Pacing sleeps may live in activities (`asyncio.sleep`); long activities heartbeat and are given a `heartbeat_timeout`.
- Workflow code must stay deterministic: no I/O, use `workflow.now()` / `workflow.sleep()`. Importing config inside `workflow.unsafe.imports_passed_through()` is the existing pattern.
- Large result sets (full floor sheet, multi-year histories) are written inside the activity — never returned through Temporal (payload size limits).
- Writers to research/natural-key tables must be idempotent upserts; timeseries snapshot tables (`market_*_snapshot`) are plain inserts.
- Per-item failures in long loops are recorded and skipped, and the summary goes into the run's `pipeline_run` message.
