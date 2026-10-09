"""Strategy Lab API — thin wrapper over the Phase 5 backtester."""

from dataclasses import asdict

from fastapi import APIRouter, Query

from backtest.engine import run_backtest
from data.historical import get_historical_bars
from strategies.registry import STRATEGY_REGISTRY, DEFAULT_LOOKBACKS

router = APIRouter()


@router.get("/strategies")
def strategies():
    return {
        "ok": True,
        "strategies": [
            {"name": name, "default_lookback": DEFAULT_LOOKBACKS.get(name, 5)}
            for name in STRATEGY_REGISTRY
        ],
    }


@router.get("/backtest")
def backtest(
    ticker: str = Query(..., description="symbol to backtest"),
    strategy: str = Query("momentum"),
    period: str = Query("1y"),
    lookback: int | None = Query(None),
    starting_equity: float = Query(10_000.0),
):
    if strategy not in STRATEGY_REGISTRY:
        return {"ok": False, "error": f"unknown strategy '{strategy}'",
                "available": list(STRATEGY_REGISTRY)}

    bars = get_historical_bars(ticker, period=period)
    if not bars.ok:
        return {"ok": False, "error": bars.error}

    fn = STRATEGY_REGISTRY[strategy]
    lb = lookback or DEFAULT_LOOKBACKS.get(strategy, 5)

    try:
        result = run_backtest(ticker.upper(), bars.bars, fn,
                               lookback=lb, starting_equity=starting_equity)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "ticker": result.ticker,
        "strategy": strategy,
        "lookback": lb,
        "period": period,
        "starting_equity": result.starting_equity,
        "ending_equity": result.ending_equity,
        "total_return_pct": result.total_return_pct,
        "buy_and_hold_return_pct": result.buy_and_hold_return_pct,
        "win_rate_pct": result.win_rate_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "trade_count": len(result.trades),
        "trades": [asdict(t) for t in result.trades],
        "equity_curve": result.equity_curve,
    }
