"""standard table and column names

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-23

Renames tables and columns so each name says what it stores, and the same
concept has the same name in every table. Rename-only: no data is rewritten
(every statement is a catalog update), and downgrade() restores the old
names exactly.

Tables are prefixed by the subsystem that owns them (market_ / news_ /
pipeline_ / app_) instead of "nepse_" (which every table is) or
"historical_"/"research_" (which didn't say news vs market data). Market
tables carry their granularity: *_snapshot = one row per live scrape,
*_daily = one row per trading day, *_tick = point observations.

    nepse_index                  -> market_index_snapshot   (read like an index master; it is live per-minute values)
    nepse_index_daily            -> market_index_daily
    nepse_intraday_tick          -> market_intraday_tick
    nepse_today_price            -> market_price_snapshot   (named after the NEPSE endpoint, not the contents)
    nepse_stock_daily            -> market_stock_daily
    nepse_security               -> market_security
    nepse_broker                 -> market_broker
    nepse_floorsheet             -> market_trade            (one row per executed trade)
    nepse_market_depth           -> market_order_book_snapshot
    nepse_sector_summary         -> market_sector_snapshot
    research_backfill_state      -> market_backfill_state   (cursors of the market-data backfills)
    nepse_news                   -> news_article            (general news portals, not NEPSE data; model was already NewsArticle)
    historical_backfill_urls     -> news_backfill_url       (all historical_* tables belong to the NEWS backfill)
    historical_backfill_progress -> news_backfill_progress
    historical_cursor_state      -> news_backfill_cursor
    historical_idwalk_cursor     -> news_backfill_idwalk_cursor
    pipeline_run_logs            -> pipeline_run            (one row per run; singular like every other table)
    admin_users                  -> app_user
    research_index_drawdown (view) -> market_index_drawdown

Columns: one name per concept across tables -- trade_date (session date;
was business_date in the snapshot/trade tables), volume (shares), turnover
(NPR), trade_count (was total_trades / total_transactions), security_id
(was stock_id in the floor sheet), broker_code (the broker number; was
member_code / buyer_member_id, easily confused with nepse_member_id, which
is NEPSE's internal id), open/high/low/close without a _price suffix, and no
unexplained abbreviations (ltp, qty).

Also: drops the accidental serial default (and its sequence) on the broker
code -- it is NEPSE's number, never generated here -- renames every primary
key, unique constraint, index and sequence to match its table, and adds
table/column comments so the schema documents itself in psql (\\dt+, \\d+).

The *_snapshot / market_trade trade_date columns stay TEXT ('YYYY-MM-DD');
converting them to DATE rewrites the 17 GB trade table and is left for a
separate migration.

Every table is locked for the (sub-second) duration of this migration, so
stop the workers and the API before running it and deploy the matching code
right after.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    ("nepse_index", "market_index_snapshot"),
    ("nepse_index_daily", "market_index_daily"),
    ("nepse_intraday_tick", "market_intraday_tick"),
    ("nepse_today_price", "market_price_snapshot"),
    ("nepse_stock_daily", "market_stock_daily"),
    ("nepse_security", "market_security"),
    ("nepse_broker", "market_broker"),
    ("nepse_floorsheet", "market_trade"),
    ("nepse_market_depth", "market_order_book_snapshot"),
    ("nepse_sector_summary", "market_sector_snapshot"),
    ("research_backfill_state", "market_backfill_state"),
    ("nepse_news", "news_article"),
    ("historical_backfill_urls", "news_backfill_url"),
    ("historical_backfill_progress", "news_backfill_progress"),
    ("historical_cursor_state", "news_backfill_cursor"),
    ("historical_idwalk_cursor", "news_backfill_idwalk_cursor"),
    ("pipeline_run_logs", "pipeline_run"),
    ("admin_users", "app_user"),
]

VIEWS = [("research_index_drawdown", "market_index_drawdown")]

# (new table name, old column, new column)
COLUMNS = [
    ("market_index_snapshot", "value", "index_value"),
    ("market_index_snapshot", "change", "point_change"),
    ("market_index_daily", "total_transactions", "trade_count"),
    ("market_stock_daily", "total_trades", "trade_count"),
    ("market_price_snapshot", "open_price", "open"),
    ("market_price_snapshot", "high_price", "high"),
    ("market_price_snapshot", "low_price", "low"),
    ("market_price_snapshot", "close_price", "close"),
    ("market_price_snapshot", "ltp", "last_traded_price"),
    ("market_price_snapshot", "total_trade_quantity", "volume"),
    ("market_price_snapshot", "total_trade_value", "turnover"),
    ("market_price_snapshot", "total_trades", "trade_count"),
    ("market_price_snapshot", "last_updated_time", "last_traded_at"),
    ("market_price_snapshot", "business_date", "trade_date"),
    ("market_trade", "stock_id", "security_id"),
    ("market_trade", "buyer_member_id", "buyer_broker_code"),
    ("market_trade", "seller_member_id", "seller_broker_code"),
    ("market_trade", "contract_quantity", "quantity"),
    ("market_trade", "contract_rate", "price"),
    ("market_trade", "contract_amount", "amount"),
    ("market_trade", "business_date", "trade_date"),
    ("market_order_book_snapshot", "total_buy_qty", "total_buy_quantity"),
    ("market_order_book_snapshot", "total_sell_qty", "total_sell_quantity"),
    ("market_sector_snapshot", "total_turnover", "turnover"),
    ("market_sector_snapshot", "total_trade_quantity", "volume"),
    ("market_sector_snapshot", "total_transactions", "trade_count"),
    ("market_sector_snapshot", "total_scrips_traded", "traded_security_count"),
    ("market_sector_snapshot", "business_date", "trade_date"),
    ("market_security", "status", "listing_status"),
    ("market_broker", "member_code", "broker_code"),
    ("market_broker", "member_name", "broker_name"),
    ("market_broker", "nepse_member_id", "nepse_internal_id"),
    ("market_backfill_state", "symbol", "item_key"),
    ("pipeline_run", "news_total", "articles_found"),
    ("pipeline_run", "news_inserted", "articles_inserted"),
    ("pipeline_run", "nepse_records", "records_written"),
    ("pipeline_run", "nepse_source", "source"),
]

# Primary keys, unique constraints and plain indexes (renaming a constraint's
# index renames the constraint too).
INDEXES = [
    ("nepse_index_pkey", "market_index_snapshot_pkey"),
    ("idx_nepse_index_name", "idx_market_index_snapshot_index_name"),
    ("idx_nepse_index_scraped_at", "idx_market_index_snapshot_scraped_at"),
    ("nepse_index_daily_pkey", "market_index_daily_pkey"),
    ("idx_nepse_index_daily_trade_date", "idx_market_index_daily_trade_date"),
    ("nepse_intraday_tick_pkey", "market_intraday_tick_pkey"),
    ("idx_nepse_intraday_tick_tick_time", "idx_market_intraday_tick_tick_time"),
    ("nepse_today_price_pkey", "market_price_snapshot_pkey"),
    ("idx_nepse_today_price_scraped_at", "idx_market_price_snapshot_scraped_at"),
    ("idx_nepse_today_price_symbol", "idx_market_price_snapshot_symbol"),
    ("nepse_stock_daily_pkey", "market_stock_daily_pkey"),
    ("idx_nepse_stock_daily_trade_date", "idx_market_stock_daily_trade_date"),
    ("nepse_security_pkey", "market_security_pkey"),
    ("idx_nepse_security_symbol", "idx_market_security_symbol"),
    ("nepse_broker_pkey", "market_broker_pkey"),
    ("nepse_floorsheet_pkey", "market_trade_pkey"),
    ("uq_nepse_floorsheet_contract", "uq_market_trade_contract_id_trade_date"),
    ("idx_nepse_floorsheet_business_date", "idx_market_trade_trade_date"),
    ("idx_nepse_floorsheet_scraped_at", "idx_market_trade_scraped_at"),
    ("idx_nepse_floorsheet_symbol", "idx_market_trade_symbol"),
    ("nepse_market_depth_pkey", "market_order_book_snapshot_pkey"),
    ("idx_nepse_market_depth_scraped_at", "idx_market_order_book_snapshot_scraped_at"),
    ("idx_nepse_market_depth_symbol", "idx_market_order_book_snapshot_symbol"),
    ("nepse_sector_summary_pkey", "market_sector_snapshot_pkey"),
    ("idx_nepse_sector_summary_name", "idx_market_sector_snapshot_sector_name"),
    ("idx_nepse_sector_summary_scraped_at", "idx_market_sector_snapshot_scraped_at"),
    ("research_backfill_state_pkey", "market_backfill_state_pkey"),
    ("nepse_news_pkey", "news_article_pkey"),
    ("nepse_news_url_key", "news_article_url_key"),
    ("idx_nepse_news_scraped_at", "idx_news_article_scraped_at"),
    ("idx_nepse_news_source", "idx_news_article_source"),
    ("idx_nepse_news_tier", "idx_news_article_portal_tier"),
    ("historical_backfill_urls_pkey", "news_backfill_url_pkey"),
    ("uq_historical_backfill_urls_source_url", "uq_news_backfill_url_source_url"),
    ("idx_historical_backfill_urls_source_status", "idx_news_backfill_url_source_status"),
    ("idx_historical_backfill_urls_source_status_rank", "idx_news_backfill_url_source_status_rank"),
    ("historical_backfill_progress_pkey", "news_backfill_progress_pkey"),
    ("uq_historical_backfill_progress_source_date", "uq_news_backfill_progress_source_target_date"),
    ("historical_cursor_state_pkey", "news_backfill_cursor_pkey"),
    ("historical_idwalk_cursor_pkey", "news_backfill_idwalk_cursor_pkey"),
    ("pipeline_run_logs_pkey", "pipeline_run_pkey"),
    ("idx_pipeline_run_logs_started_at", "idx_pipeline_run_started_at"),
    ("idx_pipeline_run_logs_status", "idx_pipeline_run_status"),
    ("admin_users_pkey", "app_user_pkey"),
    ("admin_users_email_key", "app_user_email_key"),
]

SEQUENCES = [
    ("nepse_index_id_seq", "market_index_snapshot_id_seq"),
    ("nepse_today_price_id_seq", "market_price_snapshot_id_seq"),
    ("nepse_floorsheet_id_seq", "market_trade_id_seq"),
    ("nepse_market_depth_id_seq", "market_order_book_snapshot_id_seq"),
    ("nepse_sector_summary_id_seq", "market_sector_snapshot_id_seq"),
    ("nepse_news_id_seq", "news_article_id_seq"),
    ("historical_backfill_urls_id_seq", "news_backfill_url_id_seq"),
    ("historical_backfill_progress_id_seq", "news_backfill_progress_id_seq"),
    ("pipeline_run_logs_id_seq", "pipeline_run_id_seq"),
    ("admin_users_id_seq", "app_user_id_seq"),
]

VIEW_COMMENTS = {
    "market_index_drawdown": "Per index and day over market_index_daily: log return, running peak and drawdown "
    "from it (crash ground truth).",
}

TABLE_COMMENTS = {'app_user': 'Dashboard login accounts (created with api-service manage.py create-admin).',
 'market_backfill_state': 'Resume cursors of the market-data history backfills (intraday ticks, daily '
                          'refresh, floor sheet).',
 'market_broker': 'Broker master: NEPSE trading members by broker number, with current official name.',
 'market_index_daily': 'Daily OHLC bars for all 17 NEPSE indices (NEPSE since 2000). NEPSE rows are the '
                       'trading calendar.',
 'market_index_snapshot': 'Live index values, one row per index per scrape (1-minute during market hours '
                          'since 2026-09-15).',
 'market_intraday_tick': 'Historical intraday price ticks for indices and equities since 2018-03-29 '
                         '(merolagani).',
 'market_order_book_snapshot': 'Live order-book (market depth) snapshots, up to 5 bid/ask levels, for the '
                               'most liquid securities.',
 'market_price_snapshot': "Live per-minute snapshot of every traded security's session-to-date prices and "
                          'volume.',
 'market_sector_snapshot': 'Live per-minute session-to-date turnover, volume and trade count per sector.',
 'market_security': 'Security master: every listed, suspended and delisted NEPSE security with sector and '
                    'type.',
 'market_stock_daily': 'Daily OHLCV bars for every equity incl. delisted, raw and bonus/right-adjusted '
                       '(adj_*).',
 'market_trade': 'Every executed trade (NEPSE floor sheet) with buyer/seller broker codes.',
 'news_article': 'News articles from Nepali portals (live + historical backfill), unique by url.',
 'news_backfill_cursor': 'Resume cursor per portal for cursor-paginated historical news backfills.',
 'news_backfill_idwalk_cursor': 'Next article id to fetch per portal for id-walk historical news backfills.',
 'news_backfill_progress': 'Portal/day pairs the historical news backfill has completed.',
 'news_backfill_url': 'Work queue of discovered article URLs for the historical news backfill.',
 'pipeline_run': "One row per workflow run: status, counts, timing. Read by the dashboard's Logs page."}

COLUMN_COMMENTS = {('app_user', 'password_hash'): 'bcrypt hash.',
 ('market_backfill_state', 'item_key'): "Symbol (intraday), '*' (daily_full_refresh) or session date "
                                        '(floorsheet_history).',
 ('market_broker', 'broker_code'): 'Broker number (NEPSE memberCode), as in market_trade.',
 ('market_broker', 'broker_name'): 'Current official name.',
 ('market_broker', 'active_status'): "'A' active, 'SUSPEND' suspended.",
 ('market_broker', 'nepse_internal_id'): "NEPSE's internal row id for the member -- not the broker number.",
 ('market_index_daily', 'volume'): "Shares traded across the index's constituents (official source only).",
 ('market_index_daily', 'turnover'): 'Traded value in NPR.',
 ('market_index_daily', 'trade_count'): 'Number of trades (official source only).',
 ('market_index_daily', 'source'): 'nepalstock > merolagani > csv (precedence).',
 ('market_index_snapshot', 'index_value'): 'Index level in points at scrape time.',
 ('market_index_snapshot', 'point_change'): "Change in points vs the previous session's close.",
 ('market_index_snapshot', 'percent_change'): "Change in % vs the previous session's close.",
 ('market_index_snapshot', 'scraped_at'): 'Scrape time, naive NPT.',
 ('market_intraday_tick', 'symbol'): 'Stock symbol, or index name for indices.',
 ('market_intraday_tick', 'tick_time'): 'Observation time, naive NPT.',
 ('market_intraday_tick', 'instrument_type'): "'index' or 'equity'.",
 ('market_intraday_tick', 'price'): 'Index points, or raw (unadjusted) NPR for equities.',
 ('market_intraday_tick', 'volume'): 'Equities: shares in this print. Indices: NPR turnover since the '
                                     'previous tick.',
 ('market_order_book_snapshot', 'total_buy_quantity'): 'Shares on all bid orders.',
 ('market_order_book_snapshot', 'total_sell_quantity'): 'Shares on all ask orders.',
 ('market_order_book_snapshot', 'buy_levels'): 'Bid ladder as returned by NEPSE.',
 ('market_order_book_snapshot', 'sell_levels'): 'Ask ladder as returned by NEPSE.',
 ('market_price_snapshot', 'security_id'): 'NEPSE security id (market_security).',
 ('market_price_snapshot', 'high'): 'Session high so far.',
 ('market_price_snapshot', 'low'): 'Session low so far.',
 ('market_price_snapshot', 'close'): 'Official close; NULL intraday (NEPSE sets it after the session).',
 ('market_price_snapshot', 'last_traded_price'): 'LTP at scrape time.',
 ('market_price_snapshot', 'percent_change'): 'last_traded_price vs previous_close, in %.',
 ('market_price_snapshot', 'volume'): 'Shares traded so far this session.',
 ('market_price_snapshot', 'turnover'): 'NPR traded so far this session.',
 ('market_price_snapshot', 'trade_count'): 'Trades so far this session.',
 ('market_price_snapshot', 'average_traded_price'): 'Volume-weighted average traded price so far this '
                                                    'session.',
 ('market_price_snapshot', 'last_traded_at'): "Time of this security's most recent trade (NEPSE "
                                              'lastUpdatedTime).',
 ('market_price_snapshot', 'trade_date'): "Session date as 'YYYY-MM-DD' text (NEPSE businessDate).",
 ('market_price_snapshot', 'scraped_at'): 'Scrape time, naive NPT.',
 ('market_sector_snapshot', 'turnover'): 'NPR traded so far this session.',
 ('market_sector_snapshot', 'volume'): 'Shares traded so far this session.',
 ('market_sector_snapshot', 'trade_count'): 'Trades so far this session.',
 ('market_sector_snapshot', 'traded_security_count'): 'Securities of the sector that traded this session.',
 ('market_sector_snapshot', 'trade_date'): "Session date as 'YYYY-MM-DD' text (NEPSE businessDate).",
 ('market_security', 'security_id'): "NEPSE's security id.",
 ('market_security', 'security_name'): "Name of the instrument, e.g. '11% KBL Debenture 2089'.",
 ('market_security', 'company_name'): 'Issuing company.',
 ('market_security', 'instrument_type'): 'Equity, Mutual Funds, debentures, ...',
 ('market_security', 'listing_status'): "'A' active, 'S' suspended, 'D' delisted (as reported by NEPSE).",
 ('market_stock_daily', 'volume'): 'Shares traded.',
 ('market_stock_daily', 'turnover'): 'Traded value in NPR (official source only).',
 ('market_stock_daily', 'trade_count'): 'Number of trades (official source only).',
 ('market_stock_daily', 'adj_close'): 'Bonus/right-adjusted close; use adj_* for returns. NULL until the '
                                      'weekly refresh.',
 ('market_stock_daily', 'source'): 'Source of the raw columns: nepalstock > merolagani.',
 ('market_trade', 'contract_id'): 'NEPSE contract number, unique per trade_date.',
 ('market_trade', 'security_id'): 'NEPSE security id (market_security); NULL on merolagani-backfilled '
                                  'trades.',
 ('market_trade', 'buyer_broker_code'): "Buying broker's number (market_broker.broker_code); NULL until "
                                        'after the close.',
 ('market_trade', 'seller_broker_code'): "Selling broker's number (market_broker.broker_code); NULL until "
                                         'after the close.',
 ('market_trade', 'quantity'): 'Shares traded.',
 ('market_trade', 'price'): 'Price per share in NPR (NEPSE contractRate).',
 ('market_trade', 'amount'): 'quantity x price, in NPR.',
 ('market_trade', 'trade_date'): "Session date as 'YYYY-MM-DD' text (NEPSE businessDate).",
 ('market_trade', 'trade_time'): 'Execution time as ISO text, microseconds; NULL on merolagani-backfilled '
                                 'trades.',
 ('news_article', 'source'): "Portal key, e.g. 'sharesansar'.",
 ('news_article', 'portal_tier'): "'finance' or 'general'.",
 ('news_article', 'fields_backfill_attempts'): 'Failed attempts to repair a missing published_at/body; '
                                               'capped so unfixable rows are skipped.',
 ('news_backfill_cursor', 'source'): 'Portal key, as in news_article.source.',
 ('news_backfill_cursor', 'cursor'): 'Opaque next-page cursor; NULL once exhausted.',
 ('news_backfill_idwalk_cursor', 'source'): 'Portal key, as in news_article.source.',
 ('news_backfill_progress', 'source'): 'Portal key, as in news_article.source.',
 ('news_backfill_url', 'source'): 'Portal key, as in news_article.source.',
 ('news_backfill_url', 'status'): 'pending / processing / inserted / out_of_range / failed.',
 ('news_backfill_url', 'discovery_rank'): 'Higher = probably older; claimed first.',
 ('pipeline_run', 'status'): "'success' or 'failed'.",
 ('pipeline_run', 'articles_found'): 'News runs: articles scraped.',
 ('pipeline_run', 'articles_inserted'): 'News runs: articles newly inserted.',
 ('pipeline_run', 'records_written'): 'Market runs: rows written.',
 ('pipeline_run', 'source'): "What the run used or was: the job's feed (e.g. 'nepalstock_today_price'), the "
                             "index fallback that answered, or 'none' (news runs, skipped index runs)."}


def upgrade() -> None:
    # Fail fast instead of queueing behind (and blocking) live writers.
    op.execute("SET LOCAL lock_timeout = '15s'")

    for old, new in TABLES:
        op.rename_table(old, new)
    for table, old, new in COLUMNS:
        op.alter_column(table, old, new_column_name=new)
    for old, new in INDEXES:
        op.execute(f"ALTER INDEX IF EXISTS {old} RENAME TO {new}")
    for old, new in SEQUENCES:
        op.execute(f"ALTER SEQUENCE IF EXISTS {old} RENAME TO {new}")
    for old, new in VIEWS:
        op.execute(f"ALTER VIEW {old} RENAME TO {new}")

    # The broker code is NEPSE's number, never generated here; 0012 created
    # it as a serial by accident.
    op.execute("ALTER TABLE market_broker ALTER COLUMN broker_code DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS nepse_broker_member_code_seq")

    for table, comment in TABLE_COMMENTS.items():
        op.create_table_comment(table, comment)
    for (table, column), comment in COLUMN_COMMENTS.items():
        op.alter_column(table, column, comment=comment)
    for view, comment in VIEW_COMMENTS.items():
        op.execute(f"COMMENT ON VIEW {view} IS '{comment}'")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '15s'")

    for view in VIEW_COMMENTS:
        op.execute(f"COMMENT ON VIEW {view} IS NULL")
    for (table, column) in COLUMN_COMMENTS:
        op.alter_column(table, column, comment=None)
    for table in TABLE_COMMENTS:
        op.drop_table_comment(table)

    op.execute("CREATE SEQUENCE nepse_broker_member_code_seq AS integer OWNED BY market_broker.broker_code")
    op.execute("ALTER TABLE market_broker ALTER COLUMN broker_code SET DEFAULT nextval('nepse_broker_member_code_seq')")

    for old, new in reversed(VIEWS):
        op.execute(f"ALTER VIEW {new} RENAME TO {old}")
    for old, new in reversed(SEQUENCES):
        op.execute(f"ALTER SEQUENCE IF EXISTS {new} RENAME TO {old}")
    for old, new in reversed(INDEXES):
        op.execute(f"ALTER INDEX IF EXISTS {new} RENAME TO {old}")
    for table, old, new in reversed(COLUMNS):
        op.alter_column(table, new, new_column_name=old)
    for old, new in reversed(TABLES):
        op.rename_table(new, old)
