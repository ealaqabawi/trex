"""Financial intelligence screen.

This endpoint intentionally serves ONLY what the backend actually has:
grounded whale-flow readings for the current universe plus any
research notes captured in memory. The dashboard's Intelligence screen
labels the rest as 'adapter required' so no fabricated news appears.
"""

from fastapi import APIRouter

from strategies.whale_flow import analyze_flow, format_money
from memory.repository import list_research_notes, record_research_note
from utils.trax_config import TRAX
from pydantic import BaseModel

router = APIRouter()


@router.get("/flow")
def flow():
    """Options-flow readings — the one piece of 'intelligence' this backend
    computes end-to-end today."""
    rows = []
    for symbol in TRAX.universe:
        f = analyze_flow(symbol)
        rows.append({
            "ticker": symbol,
            "ok": f.ok,
            "direction": f.direction if f.ok else "unknown",
            "net_premium": f.net_premium if f.ok else None,
            "net_premium_display": f.net_premium_display if f.ok else "n/a",
            "call_premium": f.call_premium if f.ok else None,
            "put_premium": f.put_premium if f.ok else None,
            "whale_count": len(f.whale_contracts) if f.ok else 0,
            "whales": f.whale_contracts if f.ok else [],
            "source": f.source if f.ok else None,
            "error": f.error,
        })
    return {"ok": True, "rows": rows}


@router.get("/notes")
def notes(topic: str | None = None, limit: int = 50):
    return {"ok": True, "notes": list_research_notes(limit=limit, topic=topic)}


class NoteIn(BaseModel):
    topic: str
    body: str
    source: str = ""
    tags: list[str] | None = None


@router.post("/notes")
def add_note(payload: NoteIn):
    nid = record_research_note(topic=payload.topic, body=payload.body,
                                 source=payload.source, tags=payload.tags or [])
    return {"ok": True, "id": nid}


@router.get("/sources")
def sources():
    """Explicitly enumerates which intelligence streams are adapter-ready
    and which need credentials or an authorized source. The UI reads this
    so empty sections carry a specific 'how to enable' message instead of
    showing invented data."""
    return {
        "ok": True,
        "sources": [
            {"id": "options_flow", "label": "Options flow (whales)",
             "status": "live", "detail": "yfinance chain, grounded"},
            {"id": "news", "label": "Market news",
             "status": "adapter required",
             "detail": "no connected news feed; add an authorized source (e.g. an RSS or vendor API) and implement intelligence/news_adapter.py"},
            {"id": "economic_calendar", "label": "Economic calendar",
             "status": "adapter required",
             "detail": "no feed configured; wire a Fed/BLS/econ-calendar source and implement intelligence/calendar_adapter.py"},
            {"id": "public_predictions", "label": "Public trader & AI-agent predictions",
             "status": "adapter required",
             "detail": "respect source terms, bring your own authorized feed"},
        ],
    }
