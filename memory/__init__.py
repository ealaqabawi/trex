"""Persistent research memory. SQLite-backed, lives alongside the JSON
caches from `data/store.py` without replacing them — the cache is for the
latest ingest snapshot; this is for durable observations, signals, and
experiment runs that should outlive a single cycle."""

from memory.db import (
    get_connection,
    init_db,
    DB_PATH,
)

__all__ = ["get_connection", "init_db", "DB_PATH"]
