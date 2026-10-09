"""Live Market Monitor — quotes + candles for the configured universe."""

from dataclasses import asdict

from fastapi import APIRouter, Query

from data.quotes import get_quote
from utils.market_time import session_status
from utils.trax_config import TRAX

router = APIRouter()


@router.get("/snapshot")
def snapshot():
    """Compact snapshot across the whole universe — one row per instrument."""
    rows = []
    for symbol in TRAX.universe:
        q = get_quote(symbol, interval="5m", period="1d")
        rows.append({
            "ticker": symbol,
            "ok": q.ok,
            "last_price": q.last_price,
            "previous_close": q.previous_close,
            "change": q.change,
            "change_pct": q.change_pct,
            "freshness": q.freshness_status,
            "source": q.source,
            "error": q.error,
        })
    return {"ok": True, "session": session_status().__dict__, "rows": rows}


@router.get("/{ticker}")
def quote(ticker: str, interval: str = Query("5m"), period: str = Query("1d")):
    q = get_quote(ticker, interval=interval, period=period)
    return {
        "ok": q.ok,
        "ticker": ticker.upper(),
        "last_price": q.last_price,
        "previous_close": q.previous_close,
        "change": q.change,
        "change_pct": q.change_pct,
        "freshness": q.freshness_status,
        "source": q.source,
        "bars": [asdict(b) for b in q.bars],
        "error": q.error,
    }
