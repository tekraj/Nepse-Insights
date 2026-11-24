import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


@dataclass(frozen=True)
class ScraperConfig:
    # NOTE: interval_minutes was split into news_interval_minutes and
    # nepse_interval_minutes when scraper-service was split into
    # news-service (20 news portals + news historical backfills) and
    # nepse-service (live NEPSE index + nepalstock.com.np market-data
    # scrapes). Both services import this same shared config loader --
    # the loader itself is NOT forked -- so each service just reads the
    # field it cares about.
    news_interval_minutes: int
    nepse_interval_minutes: int
    request_timeout: int
    max_articles_per_portal: int
    live_nepse_scrape_enabled: bool
    historical_daily_enabled: bool
    historical_start_date: str
    historical_daily_hour_npt: int
    historical_daily_minute_npt: int
    historical_request_timeout: int
    historical_max_records_per_portal_per_day: int
    historical_backfill_on_startup: bool
    historical_nepse_csv_import_on_startup: bool
    historical_nepse_csv_dir: str
    historical_news_backfill_enabled: bool
    nepse_news_fields_backfill_enabled: bool
    # nepse-service market-depth rotation: only the top-N most liquid
    # securities (by latest daily turnover) are walked, MARKET_DEPTH_BATCH_SIZE
    # per 1-minute tick, so each one is refreshed every ceil(N / batch)
    # minutes instead of every ~26 minutes across all ~650 listed securities.
    # 0 = walk every listed security.
    market_depth_top_n: int
    market_depth_batch_size: int
    # Research datasets (nepse-service ResearchHistoryBackfillWorkflow /
    # NepseEndOfDayWorkflow): long daily OHLCV history for every index and
    # equity plus 1-minute index bars, sourced from merolagani.com's chart
    # handler (the official nepalstock.com.np API only serves ~1 year).
    # Intraday = ~1-minute index ticks (market_intraday_tick) back to
    # intraday_backfill_start_date.
    research_backfill_enabled: bool
    research_backfill_on_startup: bool
    intraday_backfill_start_date: str
    intraday_backfill_indices: bool
    # "" = no per-stock intraday ticks, "ALL" = every active equity, or a
    # comma-separated symbol list (e.g. "NABIL,NICA,UPPER").
    intraday_backfill_stocks: str
    merolagani_request_pause_seconds: float
    # First session FloorSheetHistoryBackfillWorkflow completes (broker ids
    # + missed trades) from merolagani's floor-sheet history. Defaults to
    # the start of this project's own floor-sheet collection; merolagani has
    # data back to ~2020 (2020+ is ~100M trades, ~25-30 GB, ~1 month of
    # requests: merolagani serves old dates at 10-30 s per page).
    floorsheet_backfill_start_date: str


@dataclass(frozen=True)
class AuthConfig:
    jwt_secret: str
    jwt_ttl_minutes: int
    cookie_secure: bool


@dataclass(frozen=True)
class BiConfig:
    """business-intelligence service (agents + gRPC) and its api-service client."""
    # gRPC: the port the service listens on, and the address api-service dials.
    grpc_port: int
    grpc_address: str
    # LLM for the agents, through the generic OpenAI-compatible Chat
    # Completions API (the `openai` library): OpenAI itself, or any
    # compatible server via llm_base_url (Ollama, vLLM, LM Studio,
    # OpenRouter, Azure, ...). Without a model (and a key or base URL) the
    # agents still run and write deterministic, rule-based summaries, and
    # Q&A answers that the LLM is not configured.
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_enabled: bool
    # Structured output request style: json_schema (strict schema),
    # json_object (JSON mode) or none (schema in the prompt only); the
    # client steps down automatically when a server rejects one.
    llm_json_mode: str
    llm_temperature: float | None
    llm_max_tokens: int | None
    # Automation cadence: the refresh sweep looks for due reports every
    # report_sweep_minutes; the monitor checks prices/news every
    # monitor_interval_minutes. A report is due when its symbol's
    # refresh_minutes_live / refresh_minutes_offhours (bi_setting) elapsed,
    # its setting changed, or the monitor saw an alert-worthy event.
    report_sweep_minutes: int
    monitor_interval_minutes: int
    report_concurrency: int
    automation_enabled: bool


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    scraper: ScraperConfig
    auth: AuthConfig
    bi: BiConfig


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_auth_config() -> AuthConfig:
    return AuthConfig(
        jwt_secret=os.getenv("JWT_SECRET", "dev-only-nepse-jwt-secret-change-me"),
        jwt_ttl_minutes=int(os.getenv("JWT_TTL_MINUTES", "480")),
        cookie_secure=_env_bool("COOKIE_SECURE", False),
    )


def _load_bi_config() -> BiConfig:
    return BiConfig(
        grpc_port=int(os.getenv("BI_GRPC_PORT", "50051")),
        grpc_address=os.getenv("BI_GRPC_ADDRESS", "business-intelligence:50051"),
        llm_base_url=os.getenv("BI_LLM_BASE_URL", "").strip(),
        llm_api_key=(os.getenv("BI_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip(),
        llm_model=os.getenv("BI_LLM_MODEL", "").strip(),
        llm_enabled=_env_bool("BI_LLM_ENABLED", True)
        and bool(os.getenv("BI_LLM_MODEL", "").strip())
        and bool(os.getenv("BI_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("BI_LLM_BASE_URL")),
        llm_json_mode=os.getenv("BI_LLM_JSON_MODE", "json_schema").strip(),
        llm_temperature=float(os.environ["BI_LLM_TEMPERATURE"]) if os.getenv("BI_LLM_TEMPERATURE") else None,
        llm_max_tokens=int(os.environ["BI_LLM_MAX_TOKENS"]) if os.getenv("BI_LLM_MAX_TOKENS") else None,
        report_sweep_minutes=int(os.getenv("BI_REPORT_SWEEP_MINUTES", "5")),
        monitor_interval_minutes=int(os.getenv("BI_MONITOR_INTERVAL_MINUTES", "1")),
        report_concurrency=int(os.getenv("BI_REPORT_CONCURRENCY", "3")),
        automation_enabled=_env_bool("BI_AUTOMATION_ENABLED", True),
    )


def load_app_config() -> AppConfig:
    return AppConfig(
        database=DatabaseConfig(
            host=os.getenv("POSTGRES_HOST", "db"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "wikipedia"),
            user=os.getenv("POSTGRES_USER", "superset"),
            password=os.getenv("POSTGRES_PASSWORD", "superset_pass"),
        ),
        scraper=ScraperConfig(
            # News portal scraping cadence. Default lowered from 30 to 15
            # minutes per explicit ask -- 15 minutes also happens to divide
            # NPT's 5h45m UTC offset evenly, so it needs no NPT-alignment
            # offset in register_schedules.py (see _npt_aligned_offset there).
            news_interval_minutes=int(os.getenv("SCRAPER_INTERVAL_MINUTES", "15")),
            # NEPSE market-data scraping cadence (nepse-service): live index
            # plus the 4 nepalstock.com.np endpoints (today-price, floor
            # sheet, sector summary, market depth), all on a tight 1-minute
            # schedule since market data goes stale fast during trading hours.
            nepse_interval_minutes=int(os.getenv("NEPSE_SCRAPER_INTERVAL_MINUTES", "1")),
            request_timeout=int(os.getenv("SCRAPER_REQUEST_TIMEOUT", "15")),
            max_articles_per_portal=int(os.getenv("SCRAPER_MAX_ARTICLES_PER_PORTAL", "20")),
            live_nepse_scrape_enabled=_env_bool("LIVE_NEPSE_SCRAPE_ENABLED", False),
            historical_daily_enabled=_env_bool("HISTORICAL_DAILY_ENABLED", True),
            historical_start_date=os.getenv("HISTORICAL_START_DATE", "2020-01-01"),
            historical_daily_hour_npt=int(os.getenv("HISTORICAL_DAILY_HOUR_NPT", "2")),
            historical_daily_minute_npt=int(os.getenv("HISTORICAL_DAILY_MINUTE_NPT", "30")),
            historical_request_timeout=int(os.getenv("HISTORICAL_REQUEST_TIMEOUT", "20")),
            historical_max_records_per_portal_per_day=int(
                os.getenv("HISTORICAL_MAX_RECORDS_PER_PORTAL_PER_DAY", "50")
            ),
            historical_backfill_on_startup=_env_bool("HISTORICAL_BACKFILL_ON_STARTUP", True),
            historical_nepse_csv_import_on_startup=_env_bool(
                "HISTORICAL_NEPSE_CSV_IMPORT_ON_STARTUP", True
            ),
            historical_nepse_csv_dir=os.getenv(
                "HISTORICAL_NEPSE_CSV_DIR", "/app/historical-data"
            ),
            historical_news_backfill_enabled=_env_bool(
                "HISTORICAL_NEWS_BACKFILL_ENABLED", False
            ),
            nepse_news_fields_backfill_enabled=_env_bool(
                "NEPSE_NEWS_FIELDS_BACKFILL_ENABLED", False
            ),
            market_depth_top_n=int(os.getenv("MARKET_DEPTH_TOP_N", "50")),
            market_depth_batch_size=int(os.getenv("MARKET_DEPTH_BATCH_SIZE", "25")),
            research_backfill_enabled=_env_bool("RESEARCH_BACKFILL_ENABLED", True),
            research_backfill_on_startup=_env_bool("RESEARCH_BACKFILL_ON_STARTUP", True),
            intraday_backfill_start_date=os.getenv("INTRADAY_BACKFILL_START_DATE", "2018-01-01"),
            intraday_backfill_indices=_env_bool("INTRADAY_BACKFILL_INDICES", True),
            intraday_backfill_stocks=os.getenv("INTRADAY_BACKFILL_STOCKS", ""),
            merolagani_request_pause_seconds=float(
                os.getenv("MEROLAGANI_REQUEST_PAUSE_SECONDS", "2")
            ),
            floorsheet_backfill_start_date=os.getenv("FLOORSHEET_BACKFILL_START_DATE", "2026-09-15"),
        ),
        auth=_load_auth_config(),
        bi=_load_bi_config(),
    )
