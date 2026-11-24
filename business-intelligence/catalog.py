"""Feature catalog: every analysis the four agents can run for a script,
with its parameters. The BI Setup page renders its form from this
(GetCatalog RPC) and every save is validated against it, so bi_setting's
*_features maps only hold known feature ids with typed, in-range params.

Adding a feature: add it here, implement it in its agent, done -- no
migration and no frontend change.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str  # int | float | int_list | bool | choice
    default: Any
    min: float | None = None
    max: float | None = None
    options: tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class Feature:
    id: str
    label: str
    description: str
    level: str = "basic"  # basic | advanced; basic features are on in a new setup
    params: tuple[Param, ...] = field(default_factory=tuple)

    @property
    def default_on(self) -> bool:
        return self.level == "basic"


@dataclass(frozen=True)
class Group:
    id: str
    label: str
    agent: str
    description: str
    features: tuple[Feature, ...]


def _p(name: str, label: str, type_: str, default: Any, lo: float | None = None, hi: float | None = None, **kw: Any) -> Param:
    return Param(name, label, type_, default, lo, hi, **kw)


TECHNICAL = Group(
    "technical", "Technical analysis", "Technical agent",
    "Price action, trend, momentum and volume indicators on daily bars (plus the live session).",
    (
        Feature("candlestick", "Candlestick chart", "OHLC candlesticks instead of a close-price line."),
        Feature("volume", "Volume", "Daily volume bars with a moving average; flags unusual volume.",
                params=(_p("ma_period", "Average period", "int", 20, 5, 100),)),
        Feature("sma", "Simple moving averages", "SMA overlays; price vs. SMAs gives the trend.",
                params=(_p("periods", "Periods", "int_list", [20, 50, 200], 2, 400),)),
        Feature("ema", "Exponential moving averages", "EMA overlays, faster to react than SMAs.",
                params=(_p("periods", "Periods", "int_list", [12, 26], 2, 400),)),
        Feature("bollinger", "Bollinger Bands", "Volatility bands; %B and band squeezes.",
                params=(_p("period", "Period", "int", 20, 5, 100), _p("std", "Std. deviations", "float", 2.0, 0.5, 4))),
        Feature("rsi", "RSI", "Relative Strength Index (Wilder): overbought/oversold momentum.",
                params=(_p("period", "Period", "int", 14, 2, 50), _p("overbought", "Overbought", "float", 70, 50, 95),
                        _p("oversold", "Oversold", "float", 30, 5, 50))),
        Feature("macd", "MACD", "Moving Average Convergence Divergence: line/signal crossovers and histogram.",
                params=(_p("fast", "Fast EMA", "int", 12, 2, 50), _p("slow", "Slow EMA", "int", 26, 5, 100),
                        _p("signal", "Signal EMA", "int", 9, 2, 50))),
        Feature("stochastic", "Stochastic oscillator", "%K/%D position of the close within the recent range.",
                params=(_p("k", "%K period", "int", 14, 3, 50), _p("d", "%D period", "int", 3, 1, 20),
                        _p("smooth", "Smoothing", "int", 3, 1, 10))),
        Feature("atr", "ATR", "Average True Range: volatility in NPR, used for stop distances.",
                params=(_p("period", "Period", "int", 14, 2, 50),)),
        Feature("adx", "ADX / DMI", "Trend strength (ADX) and direction (+DI / -DI).", level="advanced",
                params=(_p("period", "Period", "int", 14, 2, 50),)),
        Feature("obv", "On-Balance Volume", "Cumulative volume flow; confirms or contradicts price trends.", level="advanced"),
        Feature("mfi", "Money Flow Index", "Volume-weighted RSI.", level="advanced",
                params=(_p("period", "Period", "int", 14, 2, 50),)),
        Feature("cci", "Commodity Channel Index", "Deviation of the typical price from its average.", level="advanced",
                params=(_p("period", "Period", "int", 20, 5, 100),)),
        Feature("williams_r", "Williams %R", "Close relative to the recent high-low range.", level="advanced",
                params=(_p("period", "Period", "int", 14, 2, 50),)),
        Feature("vwap", "Rolling VWAP", "Volume-weighted average price over N sessions.", level="advanced",
                params=(_p("period", "Sessions", "int", 20, 5, 120),)),
        Feature("ichimoku", "Ichimoku cloud", "Conversion/base lines and the cloud (support/resistance + trend).", level="advanced",
                params=(_p("tenkan", "Conversion", "int", 9, 2, 50), _p("kijun", "Base", "int", 26, 5, 100),
                        _p("senkou", "Span B", "int", 52, 10, 200))),
        Feature("support_resistance", "Support & resistance", "Price zones from clustered swing highs/lows.",
                params=(_p("lookback", "Lookback sessions", "int", 120, 30, 500), _p("levels", "Levels each side", "int", 3, 1, 6))),
        Feature("fibonacci", "Fibonacci retracements", "Retracement levels of the latest major swing.", level="advanced",
                params=(_p("lookback", "Lookback sessions", "int", 120, 20, 500),)),
        Feature("pivot_points", "Pivot points", "Classic pivots (P, R1-R3, S1-S3) for the next session.", level="advanced"),
        Feature("patterns", "Candlestick patterns", "Doji, hammer, engulfing, stars, soldiers/crows in recent bars.", level="advanced",
                params=(_p("recent", "Recent bars", "int", 10, 3, 30),)),
        Feature("trend_cross", "Golden / death cross", "Fast vs. slow SMA crossovers.",
                params=(_p("fast", "Fast SMA", "int", 50, 5, 100), _p("slow", "Slow SMA", "int", 200, 20, 400))),
        Feature("intraday", "Live session chart", "Minute-by-minute price of the current/last session."),
    ),
)

FUNDAMENTAL = Group(
    "fundamental", "Fundamental analysis", "Fundamental agent",
    "Valuation, dividends, liquidity, sector standing and broker activity (company fundamentals + floor sheet).",
    (
        Feature("valuation", "Valuation", "EPS, P/E, book value, P/BV, earnings yield, Graham value, market cap."),
        Feature("peer_valuation", "Sector valuation", "P/E, P/BV and dividend yield against the sector's peers.",
                params=(_p("max_peers", "Max peers", "int", 12, 3, 40),)),
        Feature("dividends", "Dividends & bonus", "Cash dividend / bonus history and dividend yield."),
        Feature("liquidity", "Liquidity", "Average turnover, volume trend, trades per session.",
                params=(_p("sessions", "Sessions", "int", 60, 10, 250),)),
        Feature("sector_comparison", "Sector & market performance", "Returns over 1M/3M/6M/1Y vs. sector peers and the NEPSE index."),
        Feature("broker_activity", "Broker activity", "Floor-sheet accumulation/distribution by broker, buy-side concentration.", params=(_p("days", "Days", "int", 30, 5, 180), _p("top", "Top brokers", "int", 10, 3, 25))),
        Feature("corporate_actions", "Corporate actions", "Bonus/right adjustments inferred from the adjusted-price history.",
                level="advanced"),
    ),
)

NEWS = Group(
    "news", "News analysis", "News agent",
    "Articles mentioning the script (symbol, company name, extra keywords) from ~20 Nepali portals.",
    (
        Feature("recent_news", "Company news", "Recent articles about the company.",
                params=(_p("days", "Days", "int", 30, 1, 365), _p("max_articles", "Max articles", "int", 15, 3, 40))),
        Feature("sentiment", "Sentiment & impact", "The LLM rates each article's sentiment, relevance and impact."),
        Feature("market_news", "Market-wide news", "NEPSE, SEBON, NRB and policy news that moves the whole market.",
                params=(_p("days", "Days", "int", 7, 1, 60), _p("max_articles", "Max articles", "int", 8, 3, 25))),
    ),
)

QUANT = Group(
    "quant", "Quantitative analysis", "Quant agent",
    "Statistical risk/return analysis of daily log returns (bonus/right-adjusted).",
    (
        Feature("return_stats", "Return statistics", "Annual return/volatility, Sharpe, Sortino, skew, kurtosis.",
                params=(_p("window", "Sessions", "int", 240, 60, 2400),)),
        Feature("volatility", "Volatility models", "Rolling and EWMA volatility, GARCH(1,1) forecast.",
                params=(_p("window", "Rolling window", "int", 20, 5, 120), _p("forecast_days", "Forecast horizon", "int", 10, 1, 60))),
        Feature("drawdown", "Drawdowns", "Max and current drawdown from the running peak."),
        Feature("var", "Value at Risk", "Historical, Gaussian and Cornish-Fisher VaR, plus CVaR.",
                params=(_p("confidence", "Confidence", "float", 0.95, 0.8, 0.995), _p("horizon_days", "Horizon (sessions)", "int", 1, 1, 20))),
        Feature("beta", "Beta vs. NEPSE", "Beta, correlation and alpha against the NEPSE index.",
                params=(_p("window", "Sessions", "int", 240, 60, 1200),)),
        Feature("jumps", "Jump detection", "Lee-Mykland jump test with bipower variation (jump-diffusion risk).", level="advanced", params=(_p("threshold", "Threshold", "float", 4.0, 2.5, 8.0),)),
        Feature("hurst", "Mean reversion / persistence", "Hurst exponent and variance ratios.", level="advanced"),
        Feature("monte_carlo", "Monte Carlo forecast", "Simulated price range for the coming sessions.", level="advanced",
                params=(_p("days", "Sessions ahead", "int", 20, 5, 120), _p("paths", "Paths", "int", 2000, 200, 10000),
                        _p("method", "Method", "choice", "bootstrap", options=("bootstrap", "gbm")))),
        Feature("regime", "Volatility regime", "Current volatility percentile vs. 3 years: low / normal / high / extreme.",
                level="advanced"),
        Feature("distribution", "Return distribution", "Histogram of daily returns against a normal curve.", level="advanced"),
    ),
)

GROUPS: tuple[Group, ...] = (TECHNICAL, FUNDAMENTAL, NEWS, QUANT)
GROUP_IDS = tuple(g.id for g in GROUPS)
_BY_GROUP = {g.id: {f.id: f for f in g.features} for g in GROUPS}

GENERAL = {
    "horizon": ("short", "medium", "long"),
    "risk_profile": ("conservative", "moderate", "aggressive"),
    "price_basis": ("adjusted", "raw"),
}


def catalog() -> dict[str, Any]:
    return {
        "groups": [
            {"id": g.id, "label": g.label, "agent": g.agent, "description": g.description,
             "features": [{**asdict(f), "default_on": f.default_on, "params": [asdict(p) for p in f.params]} for f in g.features]}
            for g in GROUPS
        ],
        "general": {k: list(v) for k, v in GENERAL.items()},
    }


def default_features() -> dict[str, dict[str, dict[str, Any]]]:
    return {g.id: {f.id: {p.name: p.default for p in f.params} for f in g.features if f.default_on} for g in GROUPS}


def _coerce(param: Param, value: Any) -> Any:
    if value is None:
        return param.default
    if param.type == "bool":
        return bool(value)
    if param.type == "choice":
        if value not in param.options:
            raise ValueError(f"{param.name}: must be one of {', '.join(param.options)}")
        return value
    if param.type == "int_list":
        items = value if isinstance(value, list) else [v for v in str(value).replace(";", ",").split(",") if v.strip()]
        out = sorted({int(float(v)) for v in items})
        if not out or len(out) > 6:
            raise ValueError(f"{param.name}: give 1-6 values")
        for v in out:
            _range(param, v)
        return out
    num = int(round(float(value))) if param.type == "int" else float(value)
    _range(param, num)
    return num


def _range(param: Param, v: float) -> None:
    if (param.min is not None and v < param.min) or (param.max is not None and v > param.max):
        raise ValueError(f"{param.name}: {v} is outside {param.min}..{param.max}")


def normalize_features(group: str, features: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Validate a group's feature map: known ids only, params coerced to
    their types, defaults filled, unknown params dropped. Raises ValueError
    with a readable message."""
    known = _BY_GROUP[group]
    out: dict[str, dict[str, Any]] = {}
    for fid, params in (features or {}).items():
        feature = known.get(fid)
        if feature is None:
            raise ValueError(f"Unknown {group} feature '{fid}'")
        params = params if isinstance(params, dict) else {}
        try:
            out[fid] = {p.name: _coerce(p, params.get(p.name)) for p in feature.params}
        except (TypeError, ValueError) as e:
            raise ValueError(f"{feature.label}: {e}") from e
    if group == "technical" and "macd" in out and out["macd"]["fast"] >= out["macd"]["slow"]:
        raise ValueError("MACD: the fast EMA must be shorter than the slow EMA")
    if group == "technical" and "trend_cross" in out and out["trend_cross"]["fast"] >= out["trend_cross"]["slow"]:
        raise ValueError("Golden / death cross: the fast SMA must be shorter than the slow SMA")
    if group == "technical" and "rsi" in out and out["rsi"]["oversold"] >= out["rsi"]["overbought"]:
        raise ValueError("RSI: oversold must be below overbought")
    return out


def feature_label(group: str, fid: str) -> str:
    f = _BY_GROUP.get(group, {}).get(fid)
    return f.label if f else fid
