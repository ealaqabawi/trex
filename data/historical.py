"""
Historical OHLCV data for backtesting — sourced via yfinance.

Polygon aggregates are NOT_AUTHORIZED on the current key (see
polygon_client.py), so backtesting needs its own price source independent of
that key, same reasoning as options_client.py. Bars are returned oldest-first
(unlike polygon_client's newest-first) since backtesting walks forward.
"""

from dataclasses import dataclass
from typing import Optional

from utils.logger import get_logger

log = get_logger("historical")


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class HistoricalResult:
    ok: bool
    ticker: str
    bars: list[Bar]
    error: Optional[str] = None


def get_historical_bars(ticker: str, period: str = "1y", interval: str = "1d") -> HistoricalResult:
    """`period`/`interval` follow yfinance conventions (e.g. '1y'/'1d', '6mo'/'1h')."""
    try:
        import yfinance as yf
    except ImportError:
        return HistoricalResult(ok=False, ticker=ticker, bars=[],
                                 error="yfinance not installed (pip install yfinance)")

    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df.empty:
            return HistoricalResult(ok=False, ticker=ticker, bars=[],
                                     error="no historical data returned")

        bars = [
            Bar(
                date=idx.strftime("%Y-%m-%d"),
                open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]), close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
            for idx, row in df.iterrows()
        ]
        return HistoricalResult(ok=True, ticker=ticker, bars=bars)
    except Exception as e:  # noqa: BLE001
        log.error("Historical fetch failed for %s: %s", ticker, e)
        return HistoricalResult(ok=False, ticker=ticker, bars=[], error=str(e))


def get_last_price(ticker: str) -> Optional[float]:
    """Last traded/close price via yfinance — used for position sizing when
    Polygon's price feed is unavailable."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        return float(info["lastPrice"])
    except Exception as e:  # noqa: BLE001
        log.error("Last price fetch failed for %s: %s", ticker, e)
        return None
