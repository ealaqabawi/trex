"""Rule-based fallback strategy — used when no LLM key is configured, as a
sanity check the LLM-based AnalystAgent can be compared against, and as the
first strategy wired into the Phase 5 backtester.
"""

from typing import Literal

Signal = Literal["BUY", "SELL", "HOLD"]


def _momentum_from_closes(latest_close: float, past_close: float, lookback: int) -> tuple[Signal, str]:
    pct_change = (latest_close - past_close) / past_close * 100

    if pct_change > 2:
        return "BUY", f"+{pct_change:.2f}% over last {lookback} bars"
    if pct_change < -2:
        return "SELL", f"{pct_change:.2f}% over last {lookback} bars"
    return "HOLD", f"{pct_change:+.2f}% over last {lookback} bars (within threshold)"


def momentum_signal(bars: list[dict], lookback: int = 5) -> tuple[Signal, str]:
    """Live-pipeline entry point. `bars` is Polygon aggregates results,
    newest first (dicts with a 'c' close key)."""
    if len(bars) < lookback + 1:
        return "HOLD", f"insufficient data ({len(bars)} bars, need {lookback + 1})"
    return _momentum_from_closes(bars[0]["c"], bars[lookback]["c"], lookback)


def momentum_signal_from_window(closes: list[float], lookback: int = 5) -> tuple[Signal, str]:
    """Backtest entry point. `closes` is a list of close prices, oldest
    first, ending at the current bar (as the backtester's rolling window)."""
    if len(closes) < lookback + 1:
        return "HOLD", f"insufficient data ({len(closes)} bars, need {lookback + 1})"
    return _momentum_from_closes(closes[-1], closes[-1 - lookback], lookback)
