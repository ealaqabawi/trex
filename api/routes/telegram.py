"""Telegram API — monitor + direct send/verify from TRAX.

Writes (test, send) require TRAX_ALLOW_SETTINGS_WRITE=true so a
compromised browser can't flood the user's chat. The bot token is
never serialized into any response.
"""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from memory.repository import list_telegram_history
from reports.signal_log import load_signals
from utils.alerts import send_telegram_alert, telegram_get_me
from utils.trax_config import TRAX

router = APIRouter()


def _writes_allowed() -> bool:
    return os.getenv("TRAX_ALLOW_SETTINGS_WRITE", "false").lower() == "true"


@router.get("/")
def telegram():
    history = list_telegram_history(limit=50)
    signals = load_signals()
    recent = signals[-20:] if len(signals) > 20 else signals
    verify = telegram_get_me() if TRAX.telegram_bot_token else {"ok": False, "error": "not_configured"}

    return {
        "ok": True,
        "configured": bool(TRAX.telegram_bot_token and TRAX.telegram_chat_id),
        "verify": {
            "ok": verify.get("ok", False),
            "username": verify.get("username"),
            "bot_id": verify.get("bot_id"),
            "error": verify.get("error") if not verify.get("ok") else None,
        },
        "writes_allowed": _writes_allowed(),
        "autosend": TRAX.telegram_autosend,
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


@router.get("/verify")
def verify():
    """Force a live getMe check (bypasses the 60s cache)."""
    result = telegram_get_me(force_refresh=True)
    return {
        "ok": result.get("ok", False),
        "username": result.get("username"),
        "bot_id": result.get("bot_id"),
        "error": result.get("error"),
        "detail": result.get("detail"),
    }


class TestMessage(BaseModel):
    text: Optional[str] = None


class SendMessage(BaseModel):
    text: str
    parse_mode: str = "Markdown"


@router.post("/test")
def test_send(payload: TestMessage):
    """Send a canned 'TRAX test message' to the configured chat."""
    if not _writes_allowed():
        raise HTTPException(status_code=403,
                              detail="writes are read-only; set TRAX_ALLOW_SETTINGS_WRITE=true to send")
    text = payload.text or (
        f"\U0001F7E2 *TRAX test message* — "
        f"`{datetime.now(timezone.utc).isoformat(timespec='seconds')}`\n"
        f"If you see this, your Telegram bot is wired correctly."
    )
    result = send_telegram_alert(text)
    # Never echo the token or raw response bodies that could carry it.
    return {
        "ok": result.get("ok"),
        "status_code": result.get("status_code"),
        "error": result.get("error"),
        "detail": result.get("detail"),
    }


@router.post("/send")
def send_custom(payload: SendMessage):
    """Send an arbitrary message. Writes-gate still applies."""
    if not _writes_allowed():
        raise HTTPException(status_code=403,
                              detail="writes are read-only; set TRAX_ALLOW_SETTINGS_WRITE=true to send")
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    result = send_telegram_alert(payload.text, parse_mode=payload.parse_mode)
    return {
        "ok": result.get("ok"),
        "status_code": result.get("status_code"),
        "error": result.get("error"),
        "detail": result.get("detail"),
    }
