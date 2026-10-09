"""0DTE Opportunity Scanner API."""

from dataclasses import asdict

from fastapi import APIRouter, Query

from scanner import scan_universe, scan_ticker
from memory.repository import record_scanner_candidate, list_recent_candidates
from utils.trax_config import TRAX

router = APIRouter()


@router.get("/")
def scan(
    only_0dte: bool = Query(False),
    max_dte: int = Query(7, ge=0, le=60),
    tickers: str | None = Query(None, description="comma-separated override"),
    persist: bool = Query(False, description="write every candidate to memory"),
):
    universe = ([t.strip().upper() for t in tickers.split(",") if t.strip()]
                 if tickers else list(TRAX.universe))
    candidates = scan_universe(universe, include_0dte_only=only_0dte, max_dte=max_dte)

    if persist:
        for c in candidates:
            record_scanner_candidate({
                **asdict(c),
                "rationale": " | ".join(c.rationale),
                "raw": asdict(c),
            })

    return {
        "ok": True,
        "universe": universe,
        "only_0dte": only_0dte,
        "max_dte": max_dte,
        "count": len(candidates),
        "candidates": [asdict(c) for c in candidates],
    }


@router.get("/history")
def history(limit: int = Query(50, le=500), ticker: str | None = None):
    return {
        "ok": True,
        "candidates": list_recent_candidates(limit=limit, ticker=ticker),
    }


@router.get("/{ticker}")
def ticker_scan(ticker: str, only_0dte: bool = Query(False), max_dte: int = Query(7)):
    cands = scan_ticker(ticker, include_0dte_only=only_0dte, max_dte=max_dte)
    return {"ok": True, "ticker": ticker.upper(), "count": len(cands),
            "candidates": [asdict(c) for c in cands]}
