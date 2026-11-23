"""ORM models. Table names are prefixed by the subsystem that owns them:

  market_*    NEPSE market data. Suffix = granularity: *_snapshot one row per
              live scrape (plain-insert timeseries), *_daily one row per
              trading day, *_tick point observations, no suffix = master or
              per-event table (security, broker, trade).
  news_*      news articles and the historical news backfill's bookkeeping.
  pipeline_*  workflow run log.
  app_*       dashboard application tables.
"""
from .app_user import AppUser
from .market_backfill_state import MarketBackfillState
from .market_broker import MarketBroker
from .market_index_daily import MarketIndexDaily
from .market_index_snapshot import MarketIndexSnapshot
from .market_intraday_tick import MarketIntradayTick
from .market_order_book_snapshot import MarketOrderBookSnapshot
from .market_price_snapshot import MarketPriceSnapshot
from .market_sector_snapshot import MarketSectorSnapshot
from .market_security import MarketSecurity
from .market_stock_daily import MarketStockDaily
from .market_trade import MarketTrade
from .news_article import NewsArticle
from .news_backfill_cursor import NewsBackfillCursor
from .news_backfill_idwalk_cursor import NewsBackfillIdwalkCursor
from .news_backfill_progress import NewsBackfillProgress
from .news_backfill_url import NewsBackfillUrl
from .pipeline_run import PipelineRun

__all__ = [
    "AppUser",
    "MarketBackfillState",
    "MarketBroker",
    "MarketIndexDaily",
    "MarketIndexSnapshot",
    "MarketIntradayTick",
    "MarketOrderBookSnapshot",
    "MarketPriceSnapshot",
    "MarketSectorSnapshot",
    "MarketSecurity",
    "MarketStockDaily",
    "MarketTrade",
    "NewsArticle",
    "NewsBackfillCursor",
    "NewsBackfillIdwalkCursor",
    "NewsBackfillProgress",
    "NewsBackfillUrl",
    "PipelineRun",
]
