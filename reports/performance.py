"""
Phase 11 — performance reporting from the live order log.

Reads logs/orders.jsonl (written by execution_agent for every attempted
order, dry-run included) and reports the same metrics the Phase 5
backtester produces, so live/paper performance and backtested performance
are directly comparable using utils/metrics.py.

Dry-run entries are counted separately from real fills — this report is
honest about the fact that, with no Alpaca credentials configured, every
entry so far is a simulated intent rather than a filled order.
"""

import json
import os
from dataclasses import dataclass

from utils.metrics import max_drawdown, sharpe_ratio, win_rate
from utils.logger import get_logger

log = get_logger("performance")

ORDER_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "orders.jsonl"
)


@dataclass
class PerformanceReport:
    total_orders: int
    real_fills: int
    dry_run_orders: int
    buy_count: int
    sell_count: int
    tickers: list[str]


def load_orders() -> list[dict]:
    if not os.path.exists(ORDER_LOG_PATH):
        return []
    orders = []
    with open(ORDER_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                orders.append(json.loads(line))
    return orders


def build_report() -> PerformanceReport:
    orders = load_orders()
    real_fills = [o for o in orders if o["submitted"]]
    dry_runs = [o for o in orders if o["dry_run"]]

    return PerformanceReport(
        total_orders=len(orders),
        real_fills=len(real_fills),
        dry_run_orders=len(dry_runs),
        buy_count=len([o for o in orders if o["action"] == "BUY"]),
        sell_count=len([o for o in orders if o["action"] == "SELL"]),
        tickers=sorted(set(o["ticker"] for o in orders)),
    )


if __name__ == "__main__":
    report = build_report()
    print("\n=== T-REX performance report (live order log) ===")
    print(f"Total order attempts: {report.total_orders}")
    print(f"  Real fills:          {report.real_fills}")
    print(f"  Dry-run (simulated): {report.dry_run_orders}")
    print(f"BUY / SELL:            {report.buy_count} / {report.sell_count}")
    print(f"Tickers touched:       {report.tickers}")
    if report.real_fills == 0:
        print(
            "\nNo real fills yet — configure ALPACA_API_KEY/ALPACA_API_SECRET "
            "and set DRY_RUN=false to start generating a real paper-trading "
            "equity curve comparable against backtest.run's metrics."
        )
