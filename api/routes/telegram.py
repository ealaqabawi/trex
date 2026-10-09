"""Telegram monitor — recent notifications, delivery status, duplicates."""

from fastapi import APIRouter

from memory.repository import list_telegram_history, record_telegram
from reports.signal_log import load_signals
from utils.trax_config import TRAX

router = APIRouter()


@router.get("/")
def telegram():
    history = list_telegram_history(limit=50)
    signals = load_signals()
    recent = signals[-20:] if len(signals) > 20 else signals

    return {
        "ok": True,
        "configured": bool(TRAX.telegram_bot_token and TRAX.telegram_chat_id),
        "history": history,
        "recent_signals": [
            {
                "generated_at": s.get("generated_at"), "ticker": s.get("ticker"),
                "direction": s.get("direction"), "confidence": s.get("confidence"),
                "action": s.get("action"), "outcome": s.get("outcome"),
            }
            for s in recent
        ],
        "delivery_summary": {
            "total": len(history),
            "delivered": sum(1 for h in history if h["delivered"]),
            "failed": sum(1 for h in history if not h["delivered"]),
        },
    }
