"""0DTE / near-dated opportunity scanner.

The old `strategies/contract_picker.py` is tuned for 21-45 DTE monthly
expiries — too long for the TRAX brief, which is explicitly 0DTE and
same-day expiry focused. This module reuses the shared primitives
(`num`, Black-Scholes delta, liquidity thresholds) but biases toward the
near-dated end of the chain and labels the DTE bucket in every result.

Each candidate is a research observation, NOT a trade recommendation.
A candidate becoming a published signal is a separate step gated by the
risk engine and the current `TRAX_MODE`.
"""

import math
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from typing import Optional

from data.options_client import get_options_chain
from data.quotes import get_quote
from strategies.whale_flow import num
from strategies.contract_picker import black_scholes_delta
from utils.logger import get_logger
from utils.trax_config import TRAX

log = get_logger("scanner")


# DTE buckets — the UI colours by bucket, so these labels are stable.
DTE_0 = "0DTE"
DTE_1 = "1DTE"
DTE_WEEKLY = "weekly"
DTE_MONTHLY = "monthly"
DTE_LEAP = "leap"


@dataclass
class OpportunityCandidate:
    """A near-dated option contract flagged by the scanner, with the
    rationale and the data-quality notes that drove the flag.

    `confidence` here is a composite score (0-100) over liquidity, data
    quality, and alignment with the price direction — NOT a probability
    of profit. Confidence intervals of profitability require an outcome
    dataset the scanner does not have."""
    ticker: str
    direction: str          # LONG | SHORT
    contract_type: str      # CALL | PUT
    expiration: str
    dte: int
    dte_bucket: str
    strike: float
    bid: float
    ask: float
    mid: float
    spread_pct: float
    last: float
    delta: float
    implied_vol: float
    volume: float
    open_interest: float
    volume_oi_ratio: float
    underlying_price: float
    distance_from_atm_pct: float
    contract_symbol: str
    confidence: int
    rationale: list[str]
    data_source: str
    data_quality: str
    data_freshness: str
    created_at: str = field(default_factory=lambda:
        datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _dte_days(expiration: str) -> int:
    try:
        return (datetime.strptime(expiration, "%Y-%m-%d").date() - date.today()).days
    except (ValueError, TypeError):
        return -1


def _dte_bucket(dte: int, expiration: str) -> str:
    if dte == 0:
        return DTE_0
    if dte == 1:
        return DTE_1
    if dte <= 7:
        return DTE_WEEKLY
    try:
        d = datetime.strptime(expiration, "%Y-%m-%d").date()
        if d.weekday() == 4 and 15 <= d.day <= 21 and dte <= 60:
            return DTE_MONTHLY
    except (ValueError, TypeError):
        pass
    return DTE_LEAP if dte > 90 else DTE_MONTHLY


def _assess_data_quality(bid: float, ask: float, volume: float,
                           open_interest: float) -> tuple[str, list[str]]:
    """Describes the chain row's trustworthiness. Returns (quality, notes)."""
    notes = []
    quality = "good"

    if bid <= 0 or ask <= 0:
        return "unavailable", ["bid or ask missing"]

    spread_pct = (ask - bid) / ((ask + bid) / 2) if (ask + bid) > 0 else float("inf")
    if spread_pct > 0.30:
        quality = "poor"
        notes.append(f"wide spread {spread_pct:.1%}")
    elif spread_pct > TRAX.risk.max_spread_pct:
        quality = "fair"
        notes.append(f"spread {spread_pct:.1%} above risk limit {TRAX.risk.max_spread_pct:.0%}")

    if volume < TRAX.risk.min_volume:
        quality = "poor" if quality != "unavailable" else quality
        notes.append(f"volume {int(volume)} below floor {TRAX.risk.min_volume}")

    if open_interest < TRAX.risk.min_open_interest:
        quality = "poor" if quality not in ("unavailable",) else quality
        notes.append(f"OI {int(open_interest)} below floor {TRAX.risk.min_open_interest}")

    return quality, notes


def _confidence_score(delta: float, spread_pct: float, vol_oi_ratio: float,
                       underlying_direction_bias: Optional[str],
                       contract_type: str, data_quality: str) -> int:
    """Composite 0-100. See top-of-module docstring: this is NOT a
    probability of profit, it's a liquidity+alignment score."""
    score = 0.0

    # Liquidity: tighter spread is better, saturating at 2%.
    liquidity = max(0.0, 1 - min(spread_pct / 0.20, 1.0)) * 30
    score += liquidity

    # Fresh positioning: volume meaningfully above OI reads as a new bet.
    fresh = min(vol_oi_ratio / 3.0, 1.0) * 20
    score += fresh

    # Delta sweet-spot: 0.25-0.60 absolute, bell curve around 0.45.
    abs_delta = abs(delta)
    if 0.25 <= abs_delta <= 0.60:
        score += 25 - abs(abs_delta - 0.45) * 50
    else:
        score += 0

    # Agreement with the price-side bias (if the scanner was given one).
    if underlying_direction_bias:
        aligned = (
            (underlying_direction_bias == "bullish" and contract_type == "CALL") or
            (underlying_direction_bias == "bearish" and contract_type == "PUT")
        )
        score += 15 if aligned else 0

    # Data quality floor — a poor-quality row cannot carry a high score.
    if data_quality == "poor":
        score = min(score, 40)
    elif data_quality == "fair":
        score = min(score, 65)
    elif data_quality == "unavailable":
        score = 0

    return max(0, min(100, int(round(score))))


def _rationale(bucket: str, delta: float, spread_pct: float,
                vol_oi_ratio: float, direction: str,
                data_quality: str, notes: list[str]) -> list[str]:
    out = []
    out.append(f"{bucket} contract, ~Δ{delta:+.2f}")
    out.append(f"spread {spread_pct:.1%}, volume/OI ratio {vol_oi_ratio:.1f}")
    if direction == "LONG":
        out.append("priced as a bullish same-session bet" if bucket == DTE_0
                   else "near-dated bullish positioning")
    else:
        out.append("priced as a bearish same-session bet" if bucket == DTE_0
                   else "near-dated bearish positioning")
    if data_quality != "good":
        out.append(f"data quality: {data_quality} ({'; '.join(notes)})")
    return out


def scan_ticker(
    ticker: str,
    *,
    include_0dte_only: bool = False,
    max_dte: int = 7,
    directional_bias: Optional[str] = None,
) -> list[OpportunityCandidate]:
    """Scan one ticker for near-dated option candidates.

    `directional_bias` is an optional 'bullish'/'bearish' hint from the
    price side (e.g. the Momentum signal) — the scanner uses it to boost
    the alignment component of the confidence score but does not require
    it.
    """
    quote = get_quote(ticker, interval="5m", period="1d")
    if not quote.ok or quote.last_price is None:
        log.info("scanner: %s underlying quote unavailable (%s)", ticker, quote.error)
        return []

    head = get_options_chain(ticker)
    if not head.ok or not head.expirations:
        log.info("scanner: %s has no option expirations (%s)", ticker, head.error)
        return []

    candidates: list[OpportunityCandidate] = []
    for expiration in head.expirations:
        dte = _dte_days(expiration)
        if dte < 0:
            continue
        if include_0dte_only and dte != 0:
            continue
        if dte > max_dte:
            continue

        chain = get_options_chain(ticker, expiration=expiration)
        if not chain.ok or not chain.chain:
            continue

        bucket = _dte_bucket(dte, expiration)
        for row in chain.chain:
            contract_type = (row.get("contract_type") or "").upper()
            if contract_type not in ("CALL", "PUT"):
                continue

            bid, ask = num(row.get("bid")), num(row.get("ask"))
            if bid <= 0 or ask <= 0:
                continue

            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / mid if mid > 0 else float("inf")
            volume, oi = num(row.get("volume")), num(row.get("openInterest"))
            vol_oi = volume / max(oi, 1.0)

            iv = num(row.get("impliedVolatility"))
            strike = num(row.get("strike"))
            is_call = contract_type == "CALL"
            delta = black_scholes_delta(quote.last_price, strike, iv,
                                         max(dte, 1), is_call)
            if delta == 0.0 and dte > 0:
                # Edge case: an ATM 0DTE option has zero T; fall back to a
                # crude heuristic (ITM ≈ 1.0, OTM ≈ 0.1).
                moneyness = (quote.last_price - strike) / strike
                delta = (0.9 if moneyness > 0.005 else 0.1) * (1 if is_call else -1)

            distance_pct = (strike - quote.last_price) / quote.last_price * 100

            quality, notes = _assess_data_quality(bid, ask, volume, oi)
            if quality == "unavailable":
                continue

            direction = "LONG" if is_call else "SHORT"
            score = _confidence_score(
                delta=delta, spread_pct=spread_pct, vol_oi_ratio=vol_oi,
                underlying_direction_bias=directional_bias,
                contract_type=contract_type, data_quality=quality,
            )

            if score < 20:
                continue

            candidates.append(OpportunityCandidate(
                ticker=ticker.upper(),
                direction=direction,
                contract_type=contract_type,
                expiration=expiration,
                dte=dte,
                dte_bucket=bucket,
                strike=round(strike, 2),
                bid=round(bid, 2),
                ask=round(ask, 2),
                mid=round(mid, 2),
                spread_pct=round(spread_pct, 4),
                last=round(num(row.get("lastPrice")), 2),
                delta=round(delta, 3),
                implied_vol=round(iv, 4),
                volume=volume,
                open_interest=oi,
                volume_oi_ratio=round(vol_oi, 2),
                underlying_price=round(quote.last_price, 2),
                distance_from_atm_pct=round(distance_pct, 2),
                contract_symbol=str(row.get("contractSymbol", "")),
                confidence=score,
                rationale=_rationale(bucket, delta, spread_pct, vol_oi,
                                      direction, quality, notes),
                data_source=head.source,
                data_quality=quality,
                data_freshness=quote.freshness_status,
            ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def scan_universe(
    tickers: Optional[list[str]] = None,
    *,
    include_0dte_only: bool = False,
    max_dte: int = 7,
    limit_per_ticker: int = 10,
) -> list[OpportunityCandidate]:
    tickers = tickers or list(TRAX.universe)
    out: list[OpportunityCandidate] = []
    for t in tickers:
        for cand in scan_ticker(t, include_0dte_only=include_0dte_only,
                                 max_dte=max_dte)[:limit_per_ticker]:
            out.append(cand)
    out.sort(key=lambda c: c.confidence, reverse=True)
    return out
