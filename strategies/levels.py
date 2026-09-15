"""
Entry / take-profit / stop-loss levels derived from realised volatility.

Every level is a multiple of ATR (average true range), so the targets widen
on a volatile name and tighten on a quiet one. Nothing here is a round number
picked to look good — if ATR is unavailable the caller gets None rather than
an invented level.
"""

from dataclasses import dataclass

from data.historical import Bar


@dataclass
class TradeLevels:
    direction: str          # LONG / SHORT
    entry_low: float
    entry_high: float
    tp1: float
    tp2: float
    stop_loss: float
    atr: float

    @property
    def risk_reward_tp1(self) -> float:
        risk = abs(self.entry_high - self.stop_loss) if self.direction == "LONG" \
            else abs(self.stop_loss - self.entry_low)
        reward = abs(self.tp1 - self.entry_high) if self.direction == "LONG" \
            else abs(self.entry_low - self.tp1)
        return reward / risk if risk else 0.0


def average_true_range(bars: list[Bar], period: int = 14) -> float | None:
    """Wilder's ATR. `bars` oldest-first, as data/historical.py returns them."""
    if len(bars) < period + 1:
        return None

    trs = []
    for prev, cur in zip(bars[-(period + 1):-1], bars[-period:]):
        tr = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else None


def build_levels(price: float, bars: list[Bar], direction: str,
                  entry_band: float = 0.15, tp1_r: float = 1.5,
                  tp2_r: float = 2.5, sl_mult: float = 1.25) -> TradeLevels | None:
    """Entry is a band around the current price; the stop is an ATR multiple
    below it and the targets are multiples of the *actual risk taken*.

    Targets are measured from the worst realistic fill (the far edge of the
    entry band), not from spot. Measuring from spot flattered the numbers:
    a 1xATR target with a 1xATR stop came out at 0.74:1 once the entry band
    was accounted for, i.e. risking more than TP1 paid.

    The stop is 1.25xATR rather than 1.0 because a 1xATR stop sat inside
    ordinary daily range for most names tested.
    """
    atr = average_true_range(bars)
    if not atr or price <= 0:
        return None

    band = atr * entry_band
    entry_low, entry_high = price - band, price + band

    if direction == "LONG":
        stop = entry_low - atr * sl_mult
        risk = entry_high - stop            # worst-case fill, worst-case stop
        tp1 = entry_high + risk * tp1_r
        tp2 = entry_high + risk * tp2_r
    elif direction == "SHORT":
        stop = entry_high + atr * sl_mult
        risk = stop - entry_low
        tp1 = entry_low - risk * tp1_r
        tp2 = entry_low - risk * tp2_r
    else:
        return None

    return TradeLevels(
        direction=direction,
        entry_low=round(entry_low, 2), entry_high=round(entry_high, 2),
        tp1=round(tp1, 2), tp2=round(tp2, 2), stop_loss=round(stop, 2),
        atr=round(atr, 2),
    )
