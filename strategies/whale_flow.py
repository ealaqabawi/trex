"""
Whale / large-block flow, derived from the free options chain.

Honest naming note: this is NOT dark-pool or institutional block-print data —
that needs a paid feed. What it measures is *net options premium flow*:
dollars committed to calls minus dollars committed to puts, computed as
volume x last price x 100 across the chain. Big directional bets show up
here because they cost real money to place.

"Whale" contracts are isolated separately: unusually high volume relative to
open interest (a fresh position, not churn) AND meaningful premium behind it.
"""

from dataclasses import dataclass, field

from data.options_client import get_options_chain
from utils.logger import get_logger

log = get_logger("whale_flow")

CONTRACT_MULTIPLIER = 100
WHALE_MIN_PREMIUM = 50_000       # $ committed before we call it a whale
WHALE_VOL_OI_RATIO = 3.0         # volume this many x open interest = fresh money


@dataclass
class WhaleFlow:
    ticker: str
    ok: bool
    source: str = ""
    net_premium: float = 0.0
    call_premium: float = 0.0
    put_premium: float = 0.0
    whale_contracts: list[dict] = field(default_factory=list)
    whale_call_premium: float = 0.0
    whale_put_premium: float = 0.0
    error: str | None = None

    @property
    def direction(self) -> str:
        if self.net_premium > 0:
            return "bullish"
        if self.net_premium < 0:
            return "bearish"
        return "neutral"

    @property
    def net_premium_display(self) -> str:
        return format_money(self.net_premium)


def format_money(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    v = abs(value)
    if v >= 1_000_000_000:
        return f"{sign}${v/1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{sign}${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{sign}${v/1_000:.0f}K"
    return f"{sign}${v:.0f}"


def num(value) -> float:
    """yfinance returns pandas NaN for missing fields, and `nan or 0` is nan
    because NaN is truthy — so every numeric field has to come through here."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f  # f != f is only true for NaN


def _premium(contract: dict) -> float:
    """Dollars traded in this contract today."""
    return num(contract.get("volume")) * num(contract.get("lastPrice")) * CONTRACT_MULTIPLIER


def analyze_flow(ticker: str) -> WhaleFlow:
    chain = get_options_chain(ticker)
    if not chain.ok or not chain.chain:
        return WhaleFlow(ticker=ticker, ok=False, error=chain.error)

    calls = [c for c in chain.chain if c.get("contract_type") == "call"]
    puts = [p for p in chain.chain if p.get("contract_type") == "put"]

    call_premium = sum(_premium(c) for c in calls)
    put_premium = sum(_premium(p) for p in puts)

    whales = []
    for c in chain.chain:
        premium = _premium(c)
        oi = max(num(c.get("openInterest")), 1.0)
        volume = num(c.get("volume"))
        if premium >= WHALE_MIN_PREMIUM and volume > WHALE_VOL_OI_RATIO * oi:
            whales.append({
                "contract": c.get("contractSymbol"),
                "type": c.get("contract_type"),
                "strike": num(c.get("strike")),
                "premium": premium,
                "volume": volume,
                "open_interest": num(c.get("openInterest")),
            })
    whales.sort(key=lambda w: w["premium"], reverse=True)

    return WhaleFlow(
        ticker=ticker, ok=True, source=chain.source,
        net_premium=call_premium - put_premium,
        call_premium=call_premium, put_premium=put_premium,
        whale_contracts=whales[:10],
        whale_call_premium=sum(w["premium"] for w in whales if w["type"] == "call"),
        whale_put_premium=sum(w["premium"] for w in whales if w["type"] == "put"),
    )
