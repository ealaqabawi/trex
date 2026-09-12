"""T-REX entrypoint — runs one full ingest + analyze cycle.

    python main.py                 # default watchlist
    python main.py AAPL MSFT TSLA  # custom watchlist
"""

import sys
from agents.orchestrator import run_cycle, DEFAULT_WATCHLIST

if __name__ == "__main__":
    watchlist = sys.argv[1:] or DEFAULT_WATCHLIST
    results = run_cycle(watchlist)

    print("\n=== T-REX signals ===")
    for ticker, signal in results.items():
        print(f"{ticker}: {signal}")
