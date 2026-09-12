"""
Orchestrator — manager/worker topology for Phase 4.

Runs DataIngestionAgent for each watchlist ticker, then AnalystAgent over the
freshly cached data. This is the function n8n (or cron, or main.py) calls
each cycle. Kept as plain sequential calls rather than a supervisor graph —
two workers with no shared negotiation don't need one yet; promote to a
LangGraph supervisor node if a third specialist (e.g. an execution agent)
needs to be coordinated dynamically.
"""

from agents.data_agent import ingest
from agents.analyst_agent import analyze
from utils.logger import get_logger

log = get_logger("orchestrator")

DEFAULT_WATCHLIST = ["AAPL", "NVDA", "SPY"]


def run_cycle(watchlist: list[str] | None = None) -> dict[str, str]:
    watchlist = watchlist or DEFAULT_WATCHLIST
    signals: dict[str, str] = {}

    for ticker in watchlist:
        log.info("Ingesting %s", ticker)
        ingest(ticker)

    for ticker in watchlist:
        log.info("Analyzing %s", ticker)
        signals[ticker] = analyze(ticker)

    return signals


if __name__ == "__main__":
    results = run_cycle()
    print("\n--- T-REX Phase 4 cycle results ---")
    for ticker, signal in results.items():
        print(f"{ticker}: {signal}")
