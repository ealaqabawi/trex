"""Portfolio-position persistence.

Separate from the generic repository.py so the schema and parsing logic
stay close together. Imports are append-only — every CSV drop writes a
new generation of rows with its `imported_at` timestamp, so the UI can
show "latest" without losing history.
"""

import csv
import io
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

from memory.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ParsedPosition:
    symbol: str
    quantity: float
    avg_cost: Optional[float]
    market_price: Optional[float]
    market_value: Optional[float]
    unrealized_pnl: Optional[float]
    instrument_type: Optional[str]
    currency: Optional[str]
    raw: dict


# Common brokerage column names. Order matters: the first match wins.
# Values below are lowercase; the parser lowercases headers before lookup.
SYMBOL_COLS = ["symbol", "ticker", "instrument", "code", "security", "stock", "name"]
QTY_COLS = ["quantity", "qty", "shares", "position", "contracts", "units"]
AVG_COST_COLS = ["avg cost", "avg_cost", "average cost", "cost basis", "cost", "entry", "entry price", "avg price"]
PRICE_COLS = ["market price", "last price", "price", "last", "mark", "mkt price"]
VALUE_COLS = ["market value", "mkt value", "value", "notional"]
PNL_COLS = ["unrealized pnl", "unrealized p&l", "unrealized p/l", "p&l", "pnl", "profit", "gain/loss"]
TYPE_COLS = ["type", "instrument type", "asset class", "security type"]
CURRENCY_COLS = ["currency", "ccy"]


def _pick(row: dict, candidates: list[str]) -> Optional[str]:
    for key in candidates:
        if key in row and row[key] not in ("", None):
            return str(row[key]).strip()
    return None


def _to_float(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    # Brokerage CSVs sometimes format negatives as (123.45) and use thousands
    # separators or embedded currency symbols. Strip all of that before cast.
    s = v.replace(",", "").replace("$", "").replace("USD", "").strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    return -f if neg else f


def parse_csv(contents: str) -> tuple[list[ParsedPosition], list[str]]:
    """Returns (positions, warnings). A row with no symbol or no quantity
    is skipped and warned, not silently dropped."""
    warnings: list[str] = []
    positions: list[ParsedPosition] = []

    reader = csv.DictReader(io.StringIO(contents))
    for i, raw in enumerate(reader, start=2):  # start=2 to count the header row
        lower = {(k or "").strip().lower(): v for k, v in raw.items()}

        symbol = _pick(lower, SYMBOL_COLS)
        quantity = _to_float(_pick(lower, QTY_COLS))

        if not symbol:
            warnings.append(f"row {i}: no symbol column found")
            continue
        if quantity is None:
            warnings.append(f"row {i} ({symbol}): no quantity")
            continue

        positions.append(ParsedPosition(
            symbol=symbol.upper(),
            quantity=quantity,
            avg_cost=_to_float(_pick(lower, AVG_COST_COLS)),
            market_price=_to_float(_pick(lower, PRICE_COLS)),
            market_value=_to_float(_pick(lower, VALUE_COLS)),
            unrealized_pnl=_to_float(_pick(lower, PNL_COLS)),
            instrument_type=_pick(lower, TYPE_COLS),
            currency=_pick(lower, CURRENCY_COLS),
            raw=raw,
        ))

    return positions, warnings


def record_import(positions: list[ParsedPosition], source: str,
                   filename: str = "", account_label: str = "",
                   note: str = "") -> int:
    imported_at = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO portfolio_imports
               (imported_at, source, filename, row_count, account_label, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (imported_at, source, filename, len(positions), account_label, note),
        )
        import_id = cursor.lastrowid

        for p in positions:
            conn.execute(
                """INSERT INTO portfolio_positions
                   (imported_at, source, account_label, symbol, instrument_type,
                    quantity, avg_cost, market_price, market_value,
                    unrealized_pnl, currency, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (imported_at, source, account_label, p.symbol, p.instrument_type,
                 p.quantity, p.avg_cost, p.market_price, p.market_value,
                 p.unrealized_pnl, p.currency, json.dumps(p.raw, default=str)),
            )
    return import_id


def latest_positions(account_label: Optional[str] = None) -> list[dict]:
    """Returns the most recent import's positions (optionally scoped to a
    labelled account), oldest symbol first."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(imported_at) AS latest FROM portfolio_positions"
            + (" WHERE account_label = ?" if account_label else ""),
            ((account_label,) if account_label else ()),
        ).fetchone()
        if not row or not row["latest"]:
            return []
        positions = conn.execute(
            "SELECT * FROM portfolio_positions "
            "WHERE imported_at = ? "
            + ("AND account_label = ? " if account_label else "")
            + "ORDER BY symbol",
            ((row["latest"], account_label) if account_label else (row["latest"],)),
        ).fetchall()
        return [dict(p) for p in positions]


def list_imports(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_imports ORDER BY imported_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def portfolio_summary(account_label: Optional[str] = None) -> dict:
    """Aggregate stats for the Risk Center and Overview."""
    positions = latest_positions(account_label=account_label)
    if not positions:
        return {
            "ok": True,
            "positions": [],
            "position_count": 0,
            "gross_market_value": 0.0,
            "net_market_value": 0.0,
            "unrealized_pnl": 0.0,
            "imported_at": None,
            "note": "no portfolio imported yet",
        }

    gross = sum(abs(p["market_value"] or 0) for p in positions)
    net = sum(p["market_value"] or 0 for p in positions)
    pnl = sum(p["unrealized_pnl"] or 0 for p in positions)

    return {
        "ok": True,
        "positions": positions,
        "position_count": len(positions),
        "gross_market_value": gross,
        "net_market_value": net,
        "unrealized_pnl": pnl,
        "imported_at": positions[0]["imported_at"],
    }
