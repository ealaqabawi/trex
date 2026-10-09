"""Risk engine — independent of the LLM, verifies limits reject bad orders."""

from risk.position_sizing import fixed_fractional_size
from risk.rules import check_order, RiskLimits


def test_sizing_scales_with_stop_distance():
    s1 = fixed_fractional_size(equity=10_000, entry_price=100, risk_pct=0.01,
                                stop_loss_pct=0.05)
    s2 = fixed_fractional_size(equity=10_000, entry_price=100, risk_pct=0.01,
                                stop_loss_pct=0.10)
    # Doubling the stop distance halves the share count.
    assert abs(s1.shares - 2 * s2.shares) < 0.01


def test_check_order_rejects_oversized():
    limits = RiskLimits(max_position_pct=0.20)
    result = check_order(dollar_amount=5_000, equity=10_000, open_positions=0,
                           daily_pnl_pct=0.0, limits=limits)
    assert not result.approved
    assert any("50.0%" in r or "over" in r for r in result.reasons)


def test_check_order_rejects_at_daily_loss():
    limits = RiskLimits(max_daily_loss_pct=0.03)
    result = check_order(dollar_amount=100, equity=10_000, open_positions=0,
                           daily_pnl_pct=-0.03, limits=limits)
    assert not result.approved


def test_check_order_rejects_too_many_open():
    limits = RiskLimits(max_concurrent_positions=2)
    result = check_order(dollar_amount=100, equity=10_000, open_positions=2,
                           daily_pnl_pct=0.0, limits=limits)
    assert not result.approved


def test_check_order_approves_valid():
    result = check_order(dollar_amount=1_500, equity=10_000, open_positions=1,
                           daily_pnl_pct=0.0)
    assert result.approved
