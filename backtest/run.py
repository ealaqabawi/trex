"""
Backtest CLI.

    python -m backtest.run AAPL
    python -m backtest.run AAPL --period 2y --lookback 10
"""

import argparse

from data.historical import get_historical_bars
from backtest.engine import run_backtest
from strategies.registry import get_strategy, DEFAULT_LOOKBACKS, STRATEGY_REGISTRY
from utils.logger import get_logger

log = get_logger("backtest")


def main():
    parser = argparse.ArgumentParser(description="T-REX Phase 5/6 backtester")
    parser.add_argument("ticker")
    parser.add_argument("--period", default="1y", help="yfinance period, e.g. 6mo, 1y, 2y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--strategy", default="momentum", choices=list(STRATEGY_REGISTRY))
    parser.add_argument("--lookback", type=int, default=None,
                         help="defaults to the strategy's own default lookback")
    parser.add_argument("--equity", type=float, default=10_000.0)
    args = parser.parse_args()
    lookback = args.lookback or DEFAULT_LOOKBACKS[args.strategy]

    result = get_historical_bars(args.ticker, period=args.period, interval=args.interval)
    if not result.ok:
        log.error("Could not fetch historical data for %s: %s", args.ticker, result.error)
        return

    strategy = get_strategy(args.strategy)
    strategy_fn = lambda window: strategy(window, lookback=lookback)
    bt = run_backtest(args.ticker, result.bars, strategy_fn,
                       lookback=lookback, starting_equity=args.equity)

    print(f"\n=== Backtest: {bt.ticker} | {args.strategy} (lookback={lookback}) | "
          f"{len(result.bars)} bars, {args.period}@{args.interval} ===")
    print(f"Starting equity:     ${bt.starting_equity:,.2f}")
    print(f"Ending equity:       ${bt.ending_equity:,.2f}")
    print(f"Total return:        {bt.total_return_pct:+.2f}%")
    print(f"Buy & hold return:   {bt.buy_and_hold_return_pct:+.2f}%")
    print(f"Trades:              {len(bt.trades)}")
    print(f"Win rate:            {bt.win_rate_pct:.1f}%")
    print(f"Max drawdown:        {bt.max_drawdown_pct:.2f}%")
    print(f"Sharpe ratio:        {bt.sharpe_ratio:.2f}")


if __name__ == "__main__":
    main()
