"""Portfolio-level guardrails, checked before any order proposal is allowed
through to the (paper-only) execution agent in Phase 8."""

from dataclasses import dataclass


@dataclass
class RiskLimits:
    max_position_pct: float = 0.20       # no single position over 20% of equity
    max_daily_loss_pct: float = 0.03     # halt new entries after -3% on the day
    max_concurrent_positions: int = 5


@dataclass
class RiskCheckResult:
    approved: bool
    reasons: list[str]


def check_order(
    dollar_amount: float,
    equity: float,
    open_positions: int,
    daily_pnl_pct: float,
    limits: RiskLimits = RiskLimits(),
) -> RiskCheckResult:
    reasons = []

    if equity <= 0:
        return RiskCheckResult(approved=False, reasons=["equity is zero or negative"])

    position_pct = dollar_amount / equity
    if position_pct > limits.max_position_pct:
        reasons.append(
            f"position would be {position_pct:.1%} of equity, over the "
            f"{limits.max_position_pct:.0%} limit"
        )

    if daily_pnl_pct <= -limits.max_daily_loss_pct:
        reasons.append(
            f"daily loss {daily_pnl_pct:.1%} has hit the "
            f"{limits.max_daily_loss_pct:.0%} daily loss limit — no new entries today"
        )

    if open_positions >= limits.max_concurrent_positions:
        reasons.append(
            f"{open_positions} positions already open, at the "
            f"{limits.max_concurrent_positions} concurrent-position limit"
        )

    return RiskCheckResult(approved=len(reasons) == 0, reasons=reasons)
