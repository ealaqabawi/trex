"""Portfolio API — accepts CSV exports from brokerages (Sahm, Alpaca,
IBKR, Fidelity, etc.) and exposes aggregated holdings for the dashboard.

CSV import is the sanctioned data-egress path. This endpoint deliberately
does NOT accept credentials or scrape any broker — the user clicks
Export in their broker's UI, drops the file here.
"""

from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from memory.portfolio import (
    parse_csv, record_import, portfolio_summary, list_imports, latest_positions,
)

router = APIRouter()

MAX_SIZE_BYTES = 2_000_000  # 2 MB; a portfolio CSV should never approach this


@router.get("/")
def summary(account_label: Optional[str] = None):
    """Aggregate view of the most recent import."""
    return portfolio_summary(account_label=account_label)


@router.get("/positions")
def positions(account_label: Optional[str] = None):
    rows = latest_positions(account_label=account_label)
    return {"ok": True, "count": len(rows), "positions": rows}


@router.get("/imports")
def imports():
    return {"ok": True, "imports": list_imports(limit=20)}


@router.post("/import")
async def import_csv(
    file: UploadFile = File(...),
    source: str = Form("sahm"),
    account_label: str = Form(""),
    note: str = Form(""),
):
    """Upload a broker-exported CSV. Parsed in memory, written to SQLite.

    `source` is a free-form label ('sahm', 'alpaca', 'ibkr', …) that the
    dashboard uses to tag the import. No credentials are accepted.
    """
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413,
                              detail=f"file exceeds {MAX_SIZE_BYTES} bytes")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="file encoding not recognised")

    positions, warnings = parse_csv(text)
    if not positions:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no positions parsed",
                "warnings": warnings,
                "hint": ("Expected a CSV with at least Symbol/Ticker and "
                          "Quantity/Shares columns. Headers like 'Avg Cost', "
                          "'Market Value', 'P&L', 'Currency' are also recognised."),
            },
        )

    import_id = record_import(
        positions=positions, source=source, filename=file.filename or "",
        account_label=account_label, note=note,
    )

    return {
        "ok": True,
        "import_id": import_id,
        "positions_imported": len(positions),
        "warnings": warnings,
        "source": source,
    }
