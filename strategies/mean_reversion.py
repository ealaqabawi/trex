"""Mean-reversion strategy: bets that price snaps back toward its recent
average after an outsized move, the opposite premise from momentum."""

from typing import Literal

Signal = Literal["BUY", "SELL", "HOLD"]


def mean_reversion_signal_from_window(closes: list[float], lookback: int = 20,
                                       z_threshold: float = 1.5) -> tuple[Signal, str]:
    if len(closes) < lookback + 1:
        return "HOLD", f"insufficient data ({len(closes)} bars, need {lookback + 1})"

    window = closes[-lookback:]
    mean = sum(window) / lookback
    variance = sum((c - mean) ** 2 for c in window) / lookback
    std = variance ** 0.5
    if std == 0:
        return "HOLD", "zero variance in window"

    z = (closes[-1] - mean) / std

    if z < -z_threshold:
        return "BUY", f"price {z:.2f} std below {lookback}-bar mean — expecting reversion up"
    if z > z_threshold:
        return "SELL", f"price {z:.2f} std above {lookback}-bar mean — expecting reversion down"
    return "HOLD", f"z-score {z:+.2f} within threshold"
