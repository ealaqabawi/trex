"""Lightweight JSON cache for ingested market data (data/cache/*.json).

No database dependency for Phase 4 — swap for SQLite/Postgres later without
changing the agent code, since callers only see get()/put()/latest().
"""

import json
import os
import time
from typing import Any, Optional

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.upper()}.json")


def put(ticker: str, payload: dict[str, Any]) -> None:
    record = {"ticker": ticker.upper(), "fetched_at": time.time(), **payload}
    with open(_path(ticker), "w") as f:
        json.dump(record, f, indent=2, default=str)


def latest(ticker: str) -> Optional[dict[str, Any]]:
    path = _path(ticker)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def all_cached_tickers() -> list[str]:
    return sorted(
        f[:-5] for f in os.listdir(CACHE_DIR) if f.endswith(".json")
    )
