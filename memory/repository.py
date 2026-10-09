"""Thin data-access layer over `memory/db.py`.

Keeps the SQL in one place so route handlers call `record_scanner_candidate(...)`
instead of writing SQL by hand. Returns plain dicts, not ORM objects — nothing
here warrants an ORM dependency.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from memory.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- scanner candidates ----------------------------------------------------

def record_scanner_candidate(candidate: dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO scanner_candidates
               (created_at, ticker, direction, contract_symbol, strike,
                expiration, dte, mid, spread_pct, delta, implied_vol,
                volume, open_interest, confidence, rationale, data_source,
                data_quality, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate.get("created_at", _now()),
                candidate["ticker"],
                candidate["direction"],
                candidate.get("contract_symbol"),
                candidate.get("strike"),
                candidate.get("expiration"),
                candidate.get("dte"),
                candidate.get("mid"),
                candidate.get("spread_pct"),
                candidate.get("delta"),
                candidate.get("implied_vol"),
                candidate.get("volume"),
                candidate.get("open_interest"),
                candidate.get("confidence"),
                candidate.get("rationale"),
                candidate.get("data_source"),
                candidate.get("data_quality"),
                json.dumps(candidate.get("raw", {}), default=str),
            ),
        )
        return cursor.lastrowid


def list_recent_candidates(limit: int = 50, ticker: Optional[str] = None) -> list[dict]:
    with get_connection() as conn:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM scanner_candidates WHERE ticker = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (ticker.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scanner_candidates ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# --- agent runs ------------------------------------------------------------

def start_agent_run(agent: str, task: str, model: str = "") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO agent_runs
               (started_at, agent, task, status, model)
               VALUES (?, ?, ?, 'running', ?)""",
            (_now(), agent, task, model),
        )
        return cursor.lastrowid


def finish_agent_run(run_id: int, status: str, detail: str = "", tokens: int = 0) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE agent_runs SET finished_at = ?, status = ?, detail = ?, tokens = ? "
            "WHERE id = ?",
            (_now(), status, detail, tokens, run_id),
        )


def list_agent_runs(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- risk events -----------------------------------------------------------

def record_risk_event(event_type: str, severity: str, detail: str,
                       ticker: Optional[str] = None,
                       context: Optional[dict] = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO risk_events
               (created_at, event_type, severity, ticker, detail, context_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_now(), event_type, severity, ticker, detail,
             json.dumps(context or {}, default=str)),
        )
        return cursor.lastrowid


def list_risk_events(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM risk_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- telegram history ------------------------------------------------------

def record_telegram(body: str, delivered: bool, chat_id: Optional[str] = None,
                     ticker: Optional[str] = None, direction: Optional[str] = None,
                     error: Optional[str] = None, signal_ref: Optional[str] = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO telegram_history
               (sent_at, chat_id, ticker, direction, body, delivered, error, signal_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), chat_id, ticker, direction, body, 1 if delivered else 0,
             error, signal_ref),
        )
        return cursor.lastrowid


def list_telegram_history(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM telegram_history ORDER BY sent_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- system state ----------------------------------------------------------

def set_state(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO system_state (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                               updated_at = excluded.updated_at""",
            (key, value, _now()),
        )


def get_state(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM system_state WHERE key = ?", (key,),
        ).fetchone()
        return row["value"] if row else default


# --- research notes --------------------------------------------------------

def record_research_note(topic: str, body: str, source: str = "",
                          tags: Optional[list[str]] = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO research_notes (created_at, topic, source, body, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (_now(), topic, source, body, ",".join(tags or [])),
        )
        return cursor.lastrowid


def list_research_notes(limit: int = 50, topic: Optional[str] = None) -> list[dict]:
    with get_connection() as conn:
        if topic:
            rows = conn.execute(
                "SELECT * FROM research_notes WHERE topic = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (topic, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM research_notes ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
