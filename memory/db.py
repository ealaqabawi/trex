"""SQLite-backed research memory for TRAX.

Why SQLite and not Postgres: this is a local-first platform. SQLite ships
with Python, needs no extra process, and handles our workload (append-only
signal/scan logs plus small lookup tables) without ceremony. If multi-user
hosting is ever introduced the storage adapter is small enough to swap.

Why alongside `data/store.py` and `logs/orders.jsonl`: those keep working.
This file adds a durable, queryable layer for the dashboard's needs:
scanner results, published signals with resolved outcomes, agent activity,
risk events. The order log and the JSON cache are source-of-truth for
their respective domains; this is for everything else.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "trax.sqlite3",
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS scanner_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL,
    contract_symbol TEXT,
    strike REAL,
    expiration TEXT,
    dte INTEGER,
    mid REAL,
    spread_pct REAL,
    delta REAL,
    implied_vol REAL,
    volume REAL,
    open_interest REAL,
    confidence INTEGER,
    rationale TEXT,
    data_source TEXT,
    data_quality TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_scanner_ticker ON scanner_candidates(ticker, created_at);
CREATE INDEX IF NOT EXISTS idx_scanner_time ON scanner_candidates(created_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    agent TEXT NOT NULL,
    task TEXT,
    status TEXT NOT NULL,
    detail TEXT,
    tokens INTEGER,
    model TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_time ON agent_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent, started_at);

CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    ticker TEXT,
    detail TEXT NOT NULL,
    context_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_risk_events_time ON risk_events(created_at);

CREATE TABLE IF NOT EXISTS telegram_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    chat_id TEXT,
    ticker TEXT,
    direction TEXT,
    body TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    signal_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_telegram_time ON telegram_history(sent_at);

CREATE TABLE IF NOT EXISTS research_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    topic TEXT NOT NULL,
    source TEXT,
    body TEXT NOT NULL,
    tags TEXT
);

CREATE INDEX IF NOT EXISTS idx_research_topic ON research_notes(topic, created_at);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db(db_path: str = DB_PATH) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_connection(db_path: str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yields a connection with Row row_factory and WAL mode. Callers get a
    short-lived handle rather than a module-level global, so tests can swap
    the DB path cleanly."""
    init_db(db_path)
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
