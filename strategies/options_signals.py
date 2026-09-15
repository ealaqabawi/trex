"""
Phase 12 — options-aware signals, built on the yfinance/Tradier options
chain from data/options_client.py (Polygon's options endpoint stays
unauthorized on this key, so this never touches Polygon).

Three simple, well-understood options-derived readings:
  - put/call volume ratio — crowd positioning skew
  - average implied volatility — how much movement the market is pricing in
  - unusual volume — contracts trading well above their open interest,
    often a sign of a fresh, large directional bet
"""

from dataclasses import dataclass
from typing import Literal

from data.options_client import get_options_chain
from utils.logger import get_logger

log = get_logger("options_signals")

Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass
class OptionsAnalysis:
    ticker: str
    ok: bool
    source: str = ""
    put_call_ratio: float | None = None
    avg_iv_calls: float | None = None
    avg_iv_puts: float | None = None
    unusual_volume: list[dict] | None = None
    error: str | None = None


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def analyze_chain(ticker: str, unusual_volume_multiple: float = 3.0) -> OptionsAnalysis:
    result = get_options_chain(ticker)
    if not result.ok or not result.chain:
        return OptionsAnalysis(ticker=ticker, ok=False, error=result.error)

    calls = [c for c in result.chain if c.get("contract_type") == "call"]
    puts = [c for c in result.chain if c.get("contract_type") == "put"]

    from strategies.whale_flow import num  # NaN-safe: `nan or 0` returns nan

    call_volume = sum(num(c.get("volume")) for c in calls)
    put_volume = sum(num(p.get("volume")) for p in puts)
    pcr = (put_volume / call_volume) if call_volume else None

    avg_iv_calls = _avg([num(c.get("impliedVolatility")) for c in calls if num(c.get("impliedVolatility"))])
    avg_iv_puts = _avg([num(p.get("impliedVolatility")) for p in puts if num(p.get("impliedVolatility"))])

    unusual = [
        c for c in result.chain
        if num(c.get("volume")) > unusual_volume_multiple * max(num(c.get("openInterest")), 1.0)
        and num(c.get("volume")) > 100
    ]

    return OptionsAnalysis(
        ticker=ticker, ok=True, source=result.source,
        put_call_ratio=pcr, avg_iv_calls=avg_iv_calls, avg_iv_puts=avg_iv_puts,
        unusual_volume=unusual,
    )


def options_bias_signal(ticker: str, bullish_pcr: float = 0.7, bearish_pcr: float = 1.3) -> tuple[Signal, str]:
    """A coarse positioning-skew read: heavy put volume relative to calls
    reads bearish, heavy call volume reads bullish. Meant as one input
    alongside price-based strategies, not a standalone trading signal."""
    analysis = analyze_chain(ticker)
    if not analysis.ok:
        return "HOLD", f"options data unavailable ({analysis.error})"

    if analysis.put_call_ratio is None:
        return "HOLD", "no call volume to compute put/call ratio"

    pcr = analysis.put_call_ratio
    if pcr <= bullish_pcr:
        return "BUY", f"put/call ratio {pcr:.2f} (source={analysis.source}) — call-heavy positioning"
    if pcr >= bearish_pcr:
        return "SELL", f"put/call ratio {pcr:.2f} (source={analysis.source}) — put-heavy positioning"
    return "HOLD", f"put/call ratio {pcr:.2f} — no strong skew"
