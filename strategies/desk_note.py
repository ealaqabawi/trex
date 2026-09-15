"""
Deterministic desk commentary.

Every line here is computed from the signal and the price history, so it is
true by construction. This exists because the local LLM produced a
confident, fabricated statistic ("whale influence approximately 47.31%")
from an invented formula — the tooling worked, the reasoning did not.

The observations are deliberately the ones an analyst would actually want
and a small model cannot reliably derive: how often normal daily range
would take out the stop, how concentrated the flow is, what the spread
costs on entry, and what the confidence score is actually resting on.
"""

from dataclasses import dataclass

from data.historical import Bar


@dataclass
class NoteLine:
    kind: str      # risk | flow | structure | confidence
    text: str


def _true_ranges(bars: list[Bar]) -> list[float]:
    out = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        out.append(max(cur.high - cur.low,
                        abs(cur.high - prev.close),
                        abs(cur.low - prev.close)))
    return out


def stop_noise_risk(bars: list[Bar], stop_distance: float,
                     lookback: int = 60) -> NoteLine | None:
    """How often would ordinary daily movement alone have covered the stop
    distance? This is the question 'is my stop inside the noise?' answered
    with counting rather than intuition."""
    trs = _true_ranges(bars)[-lookback:]
    if not trs or stop_distance <= 0:
        return None
    hits = sum(1 for tr in trs if tr >= stop_distance)
    pct = hits / len(trs) * 100
    verdict = ("inside normal daily noise" if pct >= 40 else
               "at the edge of normal noise" if pct >= 20 else
               "outside normal daily noise")
    return NoteLine("risk",
        f"Stop is {stop_distance:.2f} away; daily range met or exceeded that on "
        f"{hits}/{len(trs)} of the last sessions ({pct:.0f}%) — {verdict}.")


def flow_concentration(net_premium: float, top_whale: dict | None,
                        whale_count: int) -> NoteLine | None:
    """A large net premium carried by one contract is a single opinion, not
    a consensus."""
    if not top_whale or net_premium <= 0:
        return None
    share = top_whale["premium"] / net_premium * 100
    verdict = ("one contract dominates the flow — treat as a single bet"
               if share >= 50 else
               "flow is reasonably spread across contracts" if share < 25 else
               "flow is moderately concentrated")
    return NoteLine("flow",
        f"Largest single contract is {share:.0f}% of net premium "
        f"across {whale_count} whale contracts — {verdict}.")


def spread_cost(contract: dict | None) -> NoteLine | None:
    """What the bid/ask actually costs you the moment you enter."""
    if not contract or not contract.get("ok"):
        return None
    bid, ask, mid = contract["bid"], contract["ask"], contract["mid"]
    if mid <= 0:
        return None
    pct = (ask - bid) / mid * 100
    verdict = ("cheap to enter" if pct <= 3 else
               "tolerable" if pct <= 8 else "expensive — you start behind")
    return NoteLine("structure",
        f"Option spread {bid:.2f}/{ask:.2f} costs {pct:.1f}% of premium on entry — {verdict}.")


def risk_reward(levels: dict | None) -> NoteLine | None:
    if not levels:
        return None
    entry = levels["entry_high"] if levels["direction"] == "LONG" else levels["entry_low"]
    risk = abs(entry - levels["stop_loss"])
    reward = abs(levels["tp1"] - entry)
    if risk <= 0:
        return None
    rr = reward / risk
    verdict = "favourable" if rr >= 1.5 else "acceptable" if rr >= 1.0 else "poor — risking more than TP1 pays"
    return NoteLine("structure", f"TP1 risk/reward is {rr:.2f}:1 — {verdict}.")


def confidence_basis(confidence: int, components: dict) -> NoteLine | None:
    """Says out loud what the headline percentage is resting on."""
    if not components:
        return None
    history = components.get("history", 0)
    unproven = history <= 7.5
    top = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:2]
    drivers = " and ".join(k for k, _ in top)
    tail = (" History contributes only "
            f"{history:g}/15 — this setup has no resolved track record yet."
            if unproven else "")
    return NoteLine("confidence",
        f"{confidence}% rests mainly on {drivers}.{tail}")


def build_desk_note(sig, bars: list[Bar]) -> list[NoteLine]:
    """Ordered so the most decision-relevant observation comes first."""
    lines = []
    if sig.levels:
        entry = (sig.levels["entry_high"] if sig.direction == "LONG"
                 else sig.levels["entry_low"])
        dist = abs(entry - sig.levels["stop_loss"])
        if (n := stop_noise_risk(bars, dist)):
            lines.append(n)
        if (n := risk_reward(sig.levels)):
            lines.append(n)
    if (n := flow_concentration(sig.net_premium, sig.top_whale, sig.whale_count)):
        lines.append(n)
    if (n := spread_cost(sig.contract)):
        lines.append(n)
    if (n := confidence_basis(sig.confidence, sig.confidence_components)):
        lines.append(n)
    return lines


def render_note(lines: list[NoteLine]) -> str:
    return "\n".join(f"• {l.text}" for l in lines)
