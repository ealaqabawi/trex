"""Fixed-fractional position sizing: risk a fixed % of equity per trade,
sized against the distance to a stop-loss rather than just a flat share count."""

from dataclasses import dataclass


@dataclass
class PositionSize:
    shares: float
    dollar_amount: float
    risk_amount: float
    stop_loss_price: float


def fixed_fractional_size(
    equity: float,
    entry_price: float,
    risk_pct: float = 0.01,
    stop_loss_pct: float = 0.05,
) -> PositionSize:
    """Risk `risk_pct` of equity on this trade, with a stop `stop_loss_pct`
    below entry. Position size follows from how much a full stop-out costs
    per share, so a wider stop means fewer shares for the same dollar risk.
    """
    if equity <= 0 or entry_price <= 0:
        return PositionSize(shares=0, dollar_amount=0, risk_amount=0, stop_loss_price=entry_price)

    risk_amount = equity * risk_pct
    stop_loss_price = entry_price * (1 - stop_loss_pct)
    risk_per_share = entry_price - stop_loss_price

    if risk_per_share <= 0:
        return PositionSize(shares=0, dollar_amount=0, risk_amount=0, stop_loss_price=entry_price)

    shares = risk_amount / risk_per_share
    dollar_amount = shares * entry_price

    return PositionSize(
        shares=shares, dollar_amount=dollar_amount,
        risk_amount=risk_amount, stop_loss_price=stop_loss_price,
    )
