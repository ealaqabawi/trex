"""
RiskManagerAgent — turns a raw BUY/SELL/HOLD signal into a sized, risk-
checked order proposal. This agent never places an order; it only decides
whether one *may* be placed and how large. Phase 8's execution agent is the
only thing allowed to act on an approved proposal, and only against a paper
brokerage account.
"""

from dataclasses import dataclass

from risk.position_sizing import fixed_fractional_size, PositionSize
from risk.rules import check_order, RiskLimits, RiskCheckResult
from utils.logger import get_logger

log = get_logger("risk_agent")


@dataclass
class OrderProposal:
    ticker: str
    action: str  # BUY / SELL / HOLD
    approved: bool
    reasons: list[str]
    size: PositionSize | None = None


def evaluate_signal(
    ticker: str,
    signal: str,
    current_price: float,
    equity: float,
    open_positions: int = 0,
    daily_pnl_pct: float = 0.0,
    limits: RiskLimits = RiskLimits(),
) -> OrderProposal:
    if signal not in ("BUY", "SELL"):
        return OrderProposal(ticker=ticker, action="HOLD", approved=False,
                              reasons=["signal is HOLD — nothing to size or approve"])

    if signal == "SELL":
        # Sizing a sell means closing an existing position, not a new risk
        # allocation — Phase 8 looks up the actual held quantity to close.
        return OrderProposal(ticker=ticker, action="SELL", approved=True,
                              reasons=["close existing position (if any)"])

    size = fixed_fractional_size(equity=equity, entry_price=current_price)
    check = check_order(
        dollar_amount=size.dollar_amount, equity=equity,
        open_positions=open_positions, daily_pnl_pct=daily_pnl_pct, limits=limits,
    )

    if not check.approved:
        log.warning("Order proposal rejected for %s: %s", ticker, check.reasons)
    else:
        log.info("Order proposal approved for %s: %.2f shares (~$%.2f, stop @ %.2f)",
                  ticker, size.shares, size.dollar_amount, size.stop_loss_price)

    return OrderProposal(ticker=ticker, action="BUY", approved=check.approved,
                          reasons=check.reasons, size=size)
