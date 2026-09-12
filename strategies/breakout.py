"""Breakout strategy: buys when price clears its recent range high, sells
when it breaks below the recent range low (Donchian-channel style)."""

from typing import Literal

Signal = Literal["BUY", "SELL", "HOLD"]


def breakout_signal_from_window(closes: list[float], lookback: int = 20) -> tuple[Signal, str]:
    if len(closes) < lookback + 1:
        return "HOLD", f"insufficient data ({len(closes)} bars, need {lookback + 1})"

    window = closes[-(lookback + 1):-1]  # range excluding the current bar
    range_high = max(window)
    range_low = min(window)
    current = closes[-1]

    if current > range_high:
        return "BUY", f"broke above {lookback}-bar high ({range_high:.2f})"
    if current < range_low:
        return "SELL", f"broke below {lookback}-bar low ({range_low:.2f})"
    return "HOLD", f"within {lookback}-bar range [{range_low:.2f}, {range_high:.2f}]"
