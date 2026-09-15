"""
Signal confidence scoring.

Confidence is a weighted composite of four independent components, each
capped so no single one can carry a signal on its own. The breakdown is
returned alongside the score — a confidence number you can't decompose is
just a vibe with a percent sign on it.

The historical component is the feedback loop: recent realised hit-rate
pulls confidence toward reality. With no history yet it stays neutral rather
than optimistic.
"""

from dataclasses import dataclass, field

# weights sum to 100
W_MOMENTUM = 30
W_FLOW = 30
W_AGREEMENT = 25
W_HISTORY = 15


@dataclass
class ConfidenceBreakdown:
    score: int
    components: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def score_signal(
    momentum_pct: float,
    net_premium: float,
    price_signal: str,
    options_signal: str,
    hit_rate: float | None = None,
    flow_saturation: float = 5_000_000.0,
    momentum_saturation: float = 6.0,
) -> ConfidenceBreakdown:
    """
    momentum_pct      : signed % move over the lookback window
    net_premium       : signed net options premium in dollars
    price_signal      : BUY / SELL / HOLD from price momentum
    options_signal    : BUY / SELL / HOLD from options positioning
    hit_rate          : realised win rate 0..1 from past published signals
    """
    notes = []

    # 1. Momentum strength — magnitude only, saturating.
    momentum_component = _clamp(abs(momentum_pct) / momentum_saturation) * W_MOMENTUM

    # 2. Flow conviction — dollars behind the move, saturating.
    flow_component = _clamp(abs(net_premium) / flow_saturation) * W_FLOW

    # 3. Agreement — do price and options point the same way?
    if price_signal == options_signal and price_signal in ("BUY", "SELL"):
        agreement_component = float(W_AGREEMENT)
        notes.append("price and options agree")
    elif "HOLD" in (price_signal, options_signal):
        agreement_component = W_AGREEMENT * 0.4
        notes.append("one side inconclusive")
    else:
        agreement_component = 0.0
        notes.append("price and options conflict — confidence capped")

    # 4. Track record — the feedback loop.
    if hit_rate is None:
        history_component = W_HISTORY * 0.5
        notes.append("no published-signal history yet — history component neutral")
    else:
        history_component = _clamp(hit_rate) * W_HISTORY
        notes.append(f"realised hit rate {hit_rate:.0%} over past signals")

    total = momentum_component + flow_component + agreement_component + history_component

    # A conflicting signal should never read as high conviction.
    if agreement_component == 0.0:
        total = min(total, 45.0)

    return ConfidenceBreakdown(
        score=int(round(total)),
        components={
            "momentum": round(momentum_component, 1),
            "flow": round(flow_component, 1),
            "agreement": round(agreement_component, 1),
            "history": round(history_component, 1),
        },
        notes=notes,
    )
