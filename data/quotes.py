"""Thin wrapper around yfinance for intraday quotes and candle data served
to the dashboard.

Why not reuse `data/historical.py`: that module is daily-bar backtest fuel
and knows nothing about intraday 1m/5m frames. This file serves the
Live Market Monitor and the chart in each option-chain detail panel.

All results carry a `freshness` block so the UI can label delayed data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from data.freshness import classify
from utils.logger import get_logger

log = get_logger("quotes")


@dataclass
class QuoteBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class QuoteResult:
    ok: bool
    ticker: str
    last_price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    bars: list[QuoteBar] = field(default_factory=list)
    freshness_status: str = "unavailable"
    source: str = ""
    error: Optional[str] = None


_INDEX_PROXIES = {"SPX": "^GSPC", "NDX": "^NDX", "VIX": "^VIX"}


def _resolve(ticker: str) -> str:
    """Map configured universe symbols to yfinance tickers.

    SPX is an index, not a tradeable ETF; yfinance serves it as ^GSPC. The
    options chain for SPX is a separate concern — the frontend's Market
    Monitor charts the index proxy, the Options chain uses SPY as the
    tradeable proxy where SPX option feeds are unavailable.
    """
    return _INDEX_PROXIES.get(ticker.upper(), ticker.upper())


def get_quote(ticker: str, interval: str = "5m", period: str = "1d") -> QuoteResult:
    try:
        import yfinance as yf
    except ImportError:
        return QuoteResult(ok=False, ticker=ticker, error="yfinance not installed")

    symbol = _resolve(ticker)
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period=period, interval=interval)
        if df.empty:
            return QuoteResult(ok=False, ticker=ticker, source="yfinance",
                                error="no intraday bars returned")

        bars = [
            QuoteBar(
                timestamp=idx.tz_convert("UTC").isoformat() if hasattr(idx, "tz_convert")
                         else idx.isoformat(),
                open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]), close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
            for idx, row in df.iterrows()
        ]

        last = bars[-1].close
        prev_close = None
        try:
            info = tk.fast_info
            prev_close = float(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        except Exception:  # noqa: BLE001
            # fast_info is still beta; fall back to the first-bar open.
            prev_close = bars[0].open

        change = last - prev_close if prev_close else None
        change_pct = (change / prev_close * 100) if (change is not None and prev_close) else None
        fresh = classify(bars[-1].timestamp, source="yfinance")

        return QuoteResult(
            ok=True, ticker=ticker, last_price=last,
            previous_close=prev_close, change=change, change_pct=change_pct,
            bars=bars, freshness_status=fresh.status, source="yfinance",
        )
    except Exception as e:  # noqa: BLE001
        log.error("quote fetch for %s failed: %s", ticker, e)
        return QuoteResult(ok=False, ticker=ticker, source="yfinance", error=str(e))
