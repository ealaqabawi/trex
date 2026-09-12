"""
Phase 5 — backtesting engine.

Walks forward through historical bars one at a time, feeds a rolling window
of closes to a strategy function, and simulates a single-position long/flat
book (BUY opens/holds a full-equity long position, SELL closes it, HOLD does
nothing). This is intentionally simple — no shorting, no fees/slippage model,
no fractional sizing — good enough to compare strategies against each other
and against buy-and-hold before Phase 6 adds more strategies and Phase 7
adds real position sizing.
"""

from dataclasses import dataclass
from typing import Callable

from data.historical import Bar
from utils.metrics import max_drawdown, sharpe_ratio

StrategyFn = Callable[[list[float]], tuple[str, str]]


@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: str | None = None
    exit_price: float | None = None

    @property
    def pct_return(self) -> float | None:
        if self.exit_price is None:
            return None
        return (self.exit_price - self.entry_price) / self.entry_price * 100


@dataclass
class BacktestResult:
    ticker: str
    starting_equity: float
    ending_equity: float
    equity_curve: list[float]
    trades: list[Trade]
    total_return_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    buy_and_hold_return_pct: float


def run_backtest(
    ticker: str,
    bars: list[Bar],
    strategy_fn: StrategyFn,
    lookback: int = 5,
    starting_equity: float = 10_000.0,
) -> BacktestResult:
    """`bars` must be oldest-first (as returned by data/historical.py)."""
    if len(bars) < lookback + 2:
        raise ValueError(f"Need at least {lookback + 2} bars, got {len(bars)}")

    closes = [b.close for b in bars]
    equity = starting_equity
    equity_curve = [equity]
    daily_returns: list[float] = []

    position: Trade | None = None
    trades: list[Trade] = []
    shares = 0.0

    for i in range(lookback, len(bars)):
        window = closes[: i + 1]
        signal, _reason = strategy_fn(window)
        bar = bars[i]

        prev_equity = equity
        if position is not None:
            equity = shares * bar.close

        if signal == "BUY" and position is None:
            shares = equity / bar.close
            position = Trade(entry_date=bar.date, entry_price=bar.close)
        elif signal == "SELL" and position is not None:
            position.exit_date = bar.date
            position.exit_price = bar.close
            trades.append(position)
            equity = shares * bar.close
            shares = 0.0
            position = None

        equity_curve.append(equity)
        if prev_equity > 0:
            daily_returns.append((equity - prev_equity) / prev_equity)

    if position is not None:
        position.exit_date = bars[-1].date
        position.exit_price = bars[-1].close
        trades.append(position)
        equity = shares * bars[-1].close
        equity_curve[-1] = equity

    closed = [t for t in trades if t.pct_return is not None]
    wins = [t for t in closed if t.pct_return > 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0

    total_return = (equity - starting_equity) / starting_equity * 100
    buy_and_hold = (closes[-1] - closes[lookback]) / closes[lookback] * 100

    return BacktestResult(
        ticker=ticker,
        starting_equity=starting_equity,
        ending_equity=equity,
        equity_curve=equity_curve,
        trades=trades,
        total_return_pct=total_return,
        win_rate_pct=win_rate,
        max_drawdown_pct=max_drawdown(equity_curve),
        sharpe_ratio=sharpe_ratio(daily_returns),
        buy_and_hold_return_pct=buy_and_hold,
    )
