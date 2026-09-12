"""Shared performance metrics — used by both the Phase 5 backtester and the
Phase 11 live-order performance report, so backtested and live numbers are
computed the same way and are actually comparable."""

import math


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        dd = (value - peak) / peak * 100
        max_dd = min(max_dd, dd)
    return max_dd


def sharpe_ratio(daily_returns: list[float], risk_free_annual: float = 0.0) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    daily_rf = risk_free_annual / 252
    return (mean - daily_rf) / std * math.sqrt(252)


def win_rate(pct_returns: list[float]) -> float:
    if not pct_returns:
        return 0.0
    wins = [r for r in pct_returns if r > 0]
    return len(wins) / len(pct_returns) * 100
