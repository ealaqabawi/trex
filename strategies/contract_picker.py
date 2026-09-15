"""
Picks a tradeable option contract to express a directional stock signal, and
projects its premium at the stock's TP/SL levels.

Selection is liquidity-first. An option with a beautiful delta and a 30-cent
wide spread on 4 contracts of volume is untradeable, so illiquid strikes are
filtered out before anything else is considered.

Premium targets use first-order delta: dPremium ~ delta x dUnderlying. That
ignores gamma, theta and vol crush, so the projections are directionally
right and optimistic on timing — stated plainly rather than dressed up.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime

from data.options_client import get_options_chain
from strategies.whale_flow import num
from utils.logger import get_logger

log = get_logger("contract_picker")

MIN_VOLUME = 50
MIN_OPEN_INTEREST = 250
MAX_SPREAD_PCT = 0.15
TARGET_DELTA = 0.50
DTE_MIN, DTE_IDEAL_LO, DTE_IDEAL_HI = 7, 21, 45
RISK_FREE = 0.04


@dataclass
class ContractPick:
    ok: bool
    symbol: str = ""
    contract_type: str = ""
    strike: float = 0.0
    expiration: str = ""
    dte: int = 0
    bid: float = 0.0
    ask: float = 0.0
    mid: float = 0.0
    last: float = 0.0
    implied_vol: float = 0.0
    delta: float = 0.0
    volume: float = 0.0
    open_interest: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    stop: float = 0.0
    error: str | None = None


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_delta(spot: float, strike: float, iv: float, dte_days: int,
                         is_call: bool, r: float = RISK_FREE) -> float:
    """Delta from Black-Scholes. Returns 0 when inputs can't support it."""
    T = dte_days / 365.0
    if spot <= 0 or strike <= 0 or iv <= 0 or T <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    return _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0


def _dte(expiration: str) -> int:
    try:
        return (datetime.strptime(expiration, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return -1


def _is_monthly(expiration: str) -> bool:
    """Standard monthly expiry = third Friday. These carry most of the open
    interest; weeklies are often too thin to fill at a sane price."""
    try:
        d = datetime.strptime(expiration, "%Y-%m-%d").date()
    except ValueError:
        return False
    return d.weekday() == 4 and 15 <= d.day <= 21


def _choose_expiration(expirations: list[str]) -> str | None:
    """Prefer a monthly expiry in the 21-45 DTE window, then any expiry in
    that window, then the nearest with at least a week left."""
    dated = [(e, _dte(e)) for e in expirations]
    in_window = [e for e, d in dated if DTE_IDEAL_LO <= d <= DTE_IDEAL_HI]

    monthly = [e for e in in_window if _is_monthly(e)]
    if monthly:
        return monthly[0]
    if in_window:
        return in_window[0]

    later_monthly = sorted([(d, e) for e, d in dated if d >= DTE_MIN and _is_monthly(e)])
    if later_monthly:
        return later_monthly[0][1]

    viable = sorted([(d, e) for e, d in dated if d >= DTE_MIN])
    return viable[0][1] if viable else None


def pick_contract(ticker: str, direction: str, spot: float,
                   tp1: float, tp2: float, stop: float) -> ContractPick:
    if direction not in ("LONG", "SHORT"):
        return ContractPick(ok=False, error="no contract for a neutral signal")

    head = get_options_chain(ticker)
    if not head.ok or not head.expirations:
        return ContractPick(ok=False, error=head.error or "no expirations")

    expiry = _choose_expiration(head.expirations)
    if not expiry:
        return ContractPick(ok=False, error="no expiry with sufficient time left")

    chain = get_options_chain(ticker, expiration=expiry)
    if not chain.ok or not chain.chain:
        return ContractPick(ok=False, error=chain.error or "no chain for chosen expiry")

    want = "call" if direction == "LONG" else "put"
    dte = _dte(expiry)
    is_call = want == "call"

    candidates = []
    for c in chain.chain:
        if c.get("contract_type") != want:
            continue
        bid, ask = num(c.get("bid")), num(c.get("ask"))
        vol, oi = num(c.get("volume")), num(c.get("openInterest"))
        if bid <= 0 or ask <= 0:
            continue
        if vol < MIN_VOLUME or oi < MIN_OPEN_INTEREST:
            continue
        mid = (bid + ask) / 2
        if mid <= 0 or (ask - bid) / mid > MAX_SPREAD_PCT:
            continue
        iv = num(c.get("impliedVolatility"))
        delta = black_scholes_delta(spot, num(c.get("strike")), iv, dte, is_call)
        if delta == 0.0:
            continue
        candidates.append((abs(abs(delta) - TARGET_DELTA), c, mid, delta, iv, bid, ask, vol, oi))

    if not candidates:
        return ContractPick(ok=False,
                             error=f"no liquid {want}s at {expiry} "
                                   f"(need vol>={MIN_VOLUME}, OI>={MIN_OPEN_INTEREST}, "
                                   f"spread<={MAX_SPREAD_PCT:.0%})")

    candidates.sort(key=lambda x: x[0])
    _, c, mid, delta, iv, bid, ask, vol, oi = candidates[0]

    def project(target_price: float) -> float:
        return round(max(mid + delta * (target_price - spot), 0.01), 2)

    return ContractPick(
        ok=True,
        symbol=c.get("contractSymbol", ""),
        contract_type=want.upper(),
        strike=num(c.get("strike")),
        expiration=expiry, dte=dte,
        bid=round(bid, 2), ask=round(ask, 2), mid=round(mid, 2),
        last=round(num(c.get("lastPrice")), 2),
        implied_vol=round(iv, 4), delta=round(delta, 3),
        volume=vol, open_interest=oi,
        tp1=project(tp1), tp2=project(tp2), stop=project(stop),
    )
