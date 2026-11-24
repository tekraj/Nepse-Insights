from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetCatalogRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Catalog(_message.Message):
    __slots__ = ("catalog_json",)
    CATALOG_JSON_FIELD_NUMBER: _ClassVar[int]
    catalog_json: str
    def __init__(self, catalog_json: _Optional[str] = ...) -> None: ...

class SymbolRequest(_message.Message):
    __slots__ = ("symbol",)
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    def __init__(self, symbol: _Optional[str] = ...) -> None: ...

class Setting(_message.Message):
    __slots__ = ("symbol", "enabled", "horizon", "risk_profile", "price_basis", "lookback_days", "refresh_minutes_live", "refresh_minutes_offhours", "technical_enabled", "fundamental_enabled", "news_enabled", "quant_enabled", "features_json", "news_keywords", "alerts_enabled", "alert_price_change_pct", "alert_volume_spike_ratio", "alert_on_signal_change", "alert_on_news", "llm_summary_enabled", "custom_instructions", "created_at", "updated_at", "updated_by", "company_name", "sector")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    HORIZON_FIELD_NUMBER: _ClassVar[int]
    RISK_PROFILE_FIELD_NUMBER: _ClassVar[int]
    PRICE_BASIS_FIELD_NUMBER: _ClassVar[int]
    LOOKBACK_DAYS_FIELD_NUMBER: _ClassVar[int]
    REFRESH_MINUTES_LIVE_FIELD_NUMBER: _ClassVar[int]
    REFRESH_MINUTES_OFFHOURS_FIELD_NUMBER: _ClassVar[int]
    TECHNICAL_ENABLED_FIELD_NUMBER: _ClassVar[int]
    FUNDAMENTAL_ENABLED_FIELD_NUMBER: _ClassVar[int]
    NEWS_ENABLED_FIELD_NUMBER: _ClassVar[int]
    QUANT_ENABLED_FIELD_NUMBER: _ClassVar[int]
    FEATURES_JSON_FIELD_NUMBER: _ClassVar[int]
    NEWS_KEYWORDS_FIELD_NUMBER: _ClassVar[int]
    ALERTS_ENABLED_FIELD_NUMBER: _ClassVar[int]
    ALERT_PRICE_CHANGE_PCT_FIELD_NUMBER: _ClassVar[int]
    ALERT_VOLUME_SPIKE_RATIO_FIELD_NUMBER: _ClassVar[int]
    ALERT_ON_SIGNAL_CHANGE_FIELD_NUMBER: _ClassVar[int]
    ALERT_ON_NEWS_FIELD_NUMBER: _ClassVar[int]
    LLM_SUMMARY_ENABLED_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_BY_FIELD_NUMBER: _ClassVar[int]
    COMPANY_NAME_FIELD_NUMBER: _ClassVar[int]
    SECTOR_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    enabled: bool
    horizon: str
    risk_profile: str
    price_basis: str
    lookback_days: int
    refresh_minutes_live: int
    refresh_minutes_offhours: int
    technical_enabled: bool
    fundamental_enabled: bool
    news_enabled: bool
    quant_enabled: bool
    features_json: str
    news_keywords: _containers.RepeatedScalarFieldContainer[str]
    alerts_enabled: bool
    alert_price_change_pct: float
    alert_volume_spike_ratio: float
    alert_on_signal_change: bool
    alert_on_news: bool
    llm_summary_enabled: bool
    custom_instructions: str
    created_at: str
    updated_at: str
    updated_by: str
    company_name: str
    sector: str
    def __init__(self, symbol: _Optional[str] = ..., enabled: _Optional[bool] = ..., horizon: _Optional[str] = ..., risk_profile: _Optional[str] = ..., price_basis: _Optional[str] = ..., lookback_days: _Optional[int] = ..., refresh_minutes_live: _Optional[int] = ..., refresh_minutes_offhours: _Optional[int] = ..., technical_enabled: _Optional[bool] = ..., fundamental_enabled: _Optional[bool] = ..., news_enabled: _Optional[bool] = ..., quant_enabled: _Optional[bool] = ..., features_json: _Optional[str] = ..., news_keywords: _Optional[_Iterable[str]] = ..., alerts_enabled: _Optional[bool] = ..., alert_price_change_pct: _Optional[float] = ..., alert_volume_spike_ratio: _Optional[float] = ..., alert_on_signal_change: _Optional[bool] = ..., alert_on_news: _Optional[bool] = ..., llm_summary_enabled: _Optional[bool] = ..., custom_instructions: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., updated_by: _Optional[str] = ..., company_name: _Optional[str] = ..., sector: _Optional[str] = ...) -> None: ...

class ListSettingsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListSettingsResponse(_message.Message):
    __slots__ = ("settings",)
    SETTINGS_FIELD_NUMBER: _ClassVar[int]
    settings: _containers.RepeatedCompositeFieldContainer[Setting]
    def __init__(self, settings: _Optional[_Iterable[_Union[Setting, _Mapping]]] = ...) -> None: ...

class UpsertSettingRequest(_message.Message):
    __slots__ = ("setting", "user")
    SETTING_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    setting: Setting
    user: str
    def __init__(self, setting: _Optional[_Union[Setting, _Mapping]] = ..., user: _Optional[str] = ...) -> None: ...

class DeleteSettingResponse(_message.Message):
    __slots__ = ("deleted",)
    DELETED_FIELD_NUMBER: _ClassVar[int]
    deleted: bool
    def __init__(self, deleted: _Optional[bool] = ...) -> None: ...

class ReportSummary(_message.Message):
    __slots__ = ("symbol", "company_name", "sector", "enabled", "status", "recommendation", "score", "confidence", "headline", "last_price", "generated_at", "data_as_of")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    COMPANY_NAME_FIELD_NUMBER: _ClassVar[int]
    SECTOR_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RECOMMENDATION_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    HEADLINE_FIELD_NUMBER: _ClassVar[int]
    LAST_PRICE_FIELD_NUMBER: _ClassVar[int]
    GENERATED_AT_FIELD_NUMBER: _ClassVar[int]
    DATA_AS_OF_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    company_name: str
    sector: str
    enabled: bool
    status: str
    recommendation: str
    score: float
    confidence: float
    headline: str
    last_price: float
    generated_at: str
    data_as_of: str
    def __init__(self, symbol: _Optional[str] = ..., company_name: _Optional[str] = ..., sector: _Optional[str] = ..., enabled: _Optional[bool] = ..., status: _Optional[str] = ..., recommendation: _Optional[str] = ..., score: _Optional[float] = ..., confidence: _Optional[float] = ..., headline: _Optional[str] = ..., last_price: _Optional[float] = ..., generated_at: _Optional[str] = ..., data_as_of: _Optional[str] = ...) -> None: ...

class ListReportsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListReportsResponse(_message.Message):
    __slots__ = ("reports", "llm_enabled")
    REPORTS_FIELD_NUMBER: _ClassVar[int]
    LLM_ENABLED_FIELD_NUMBER: _ClassVar[int]
    reports: _containers.RepeatedCompositeFieldContainer[ReportSummary]
    llm_enabled: bool
    def __init__(self, reports: _Optional[_Iterable[_Union[ReportSummary, _Mapping]]] = ..., llm_enabled: _Optional[bool] = ...) -> None: ...

class Report(_message.Message):
    __slots__ = ("summary", "exists", "report_json")
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    REPORT_JSON_FIELD_NUMBER: _ClassVar[int]
    summary: ReportSummary
    exists: bool
    report_json: str
    def __init__(self, summary: _Optional[_Union[ReportSummary, _Mapping]] = ..., exists: _Optional[bool] = ..., report_json: _Optional[str] = ...) -> None: ...

class RefreshReportResponse(_message.Message):
    __slots__ = ("queued", "workflow_id", "message")
    QUEUED_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    queued: bool
    workflow_id: str
    message: str
    def __init__(self, queued: _Optional[bool] = ..., workflow_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class ChatTurn(_message.Message):
    __slots__ = ("role", "content")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    role: str
    content: str
    def __init__(self, role: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class AskRequest(_message.Message):
    __slots__ = ("symbol", "question", "history", "user")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    QUESTION_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    question: str
    history: _containers.RepeatedCompositeFieldContainer[ChatTurn]
    user: str
    def __init__(self, symbol: _Optional[str] = ..., question: _Optional[str] = ..., history: _Optional[_Iterable[_Union[ChatTurn, _Mapping]]] = ..., user: _Optional[str] = ...) -> None: ...

class ToolStatus(_message.Message):
    __slots__ = ("name", "label", "state")
    NAME_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    name: str
    label: str
    state: str
    def __init__(self, name: _Optional[str] = ..., label: _Optional[str] = ..., state: _Optional[str] = ...) -> None: ...

class AskDone(_message.Message):
    __slots__ = ("model", "input_tokens", "output_tokens", "sources")
    MODEL_FIELD_NUMBER: _ClassVar[int]
    INPUT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    model: str
    input_tokens: int
    output_tokens: int
    sources: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, model: _Optional[str] = ..., input_tokens: _Optional[int] = ..., output_tokens: _Optional[int] = ..., sources: _Optional[_Iterable[str]] = ...) -> None: ...

class AskEvent(_message.Message):
    __slots__ = ("text_delta", "tool", "done", "error")
    TEXT_DELTA_FIELD_NUMBER: _ClassVar[int]
    TOOL_FIELD_NUMBER: _ClassVar[int]
    DONE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    text_delta: str
    tool: ToolStatus
    done: AskDone
    error: str
    def __init__(self, text_delta: _Optional[str] = ..., tool: _Optional[_Union[ToolStatus, _Mapping]] = ..., done: _Optional[_Union[AskDone, _Mapping]] = ..., error: _Optional[str] = ...) -> None: ...

class Notification(_message.Message):
    __slots__ = ("id", "symbol", "kind", "severity", "title", "body", "data_json", "created_at", "read")
    ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    READ_FIELD_NUMBER: _ClassVar[int]
    id: int
    symbol: str
    kind: str
    severity: str
    title: str
    body: str
    data_json: str
    created_at: str
    read: bool
    def __init__(self, id: _Optional[int] = ..., symbol: _Optional[str] = ..., kind: _Optional[str] = ..., severity: _Optional[str] = ..., title: _Optional[str] = ..., body: _Optional[str] = ..., data_json: _Optional[str] = ..., created_at: _Optional[str] = ..., read: _Optional[bool] = ...) -> None: ...

class ListNotificationsRequest(_message.Message):
    __slots__ = ("symbol", "unread_only", "limit")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    UNREAD_ONLY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    unread_only: bool
    limit: int
    def __init__(self, symbol: _Optional[str] = ..., unread_only: _Optional[bool] = ..., limit: _Optional[int] = ...) -> None: ...

class ListNotificationsResponse(_message.Message):
    __slots__ = ("notifications", "unread_count")
    NOTIFICATIONS_FIELD_NUMBER: _ClassVar[int]
    UNREAD_COUNT_FIELD_NUMBER: _ClassVar[int]
    notifications: _containers.RepeatedCompositeFieldContainer[Notification]
    unread_count: int
    def __init__(self, notifications: _Optional[_Iterable[_Union[Notification, _Mapping]]] = ..., unread_count: _Optional[int] = ...) -> None: ...

class MarkNotificationsReadRequest(_message.Message):
    __slots__ = ("ids", "all", "symbol")
    IDS_FIELD_NUMBER: _ClassVar[int]
    ALL_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    ids: _containers.RepeatedScalarFieldContainer[int]
    all: bool
    symbol: str
    def __init__(self, ids: _Optional[_Iterable[int]] = ..., all: _Optional[bool] = ..., symbol: _Optional[str] = ...) -> None: ...

class MarkNotificationsReadResponse(_message.Message):
    __slots__ = ("updated",)
    UPDATED_FIELD_NUMBER: _ClassVar[int]
    updated: int
    def __init__(self, updated: _Optional[int] = ...) -> None: ...

class PortfolioRequest(_message.Message):
    __slots__ = ("user", "request_json")
    USER_FIELD_NUMBER: _ClassVar[int]
    REQUEST_JSON_FIELD_NUMBER: _ClassVar[int]
    user: str
    request_json: str
    def __init__(self, user: _Optional[str] = ..., request_json: _Optional[str] = ...) -> None: ...

class PortfolioProgress(_message.Message):
    __slots__ = ("stage", "message", "fraction")
    STAGE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    FRACTION_FIELD_NUMBER: _ClassVar[int]
    stage: str
    message: str
    fraction: float
    def __init__(self, stage: _Optional[str] = ..., message: _Optional[str] = ..., fraction: _Optional[float] = ...) -> None: ...

class PortfolioEvent(_message.Message):
    __slots__ = ("progress", "portfolio_json", "error")
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    PORTFOLIO_JSON_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    progress: PortfolioProgress
    portfolio_json: str
    error: str
    def __init__(self, progress: _Optional[_Union[PortfolioProgress, _Mapping]] = ..., portfolio_json: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class PortfolioQuery(_message.Message):
    __slots__ = ("user",)
    USER_FIELD_NUMBER: _ClassVar[int]
    user: str
    def __init__(self, user: _Optional[str] = ...) -> None: ...

class PortfolioResult(_message.Message):
    __slots__ = ("exists", "portfolio_json")
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    PORTFOLIO_JSON_FIELD_NUMBER: _ClassVar[int]
    exists: bool
    portfolio_json: str
    def __init__(self, exists: _Optional[bool] = ..., portfolio_json: _Optional[str] = ...) -> None: ...
