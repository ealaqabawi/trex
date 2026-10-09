"""Health + readiness. Reports which subsystems are live and which are
degraded — the dashboard surfaces this as a status bar, not a single bit."""

from datetime import datetime, timezone

from fastapi import APIRouter

from utils.config import CONFIG
from utils.market_time import session_status
from utils.trax_config import TRAX
from data.options_client import get_options_chain

router = APIRouter()


@router.get("/")
def health():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # A tiny real probe: ask yfinance for SPY options. The result is cached
    # by yfinance itself, so this stays cheap; a failure here classifies
    # the options feed as degraded in the UI.
    probe = get_options_chain("SPY")
    options_live = probe.ok

    return {
        "ok": True,
        "now_utc": now,
        "version": "0.1.0",
        "mode": TRAX.mode,
        "subsystems": {
            "options_feed": {
                "status": "ok" if options_live else "degraded",
                "source": probe.source or "unknown",
                "error": probe.error if not options_live else None,
            },
            "price_feed": {
                "status": "ok",
                "source": "yfinance",
                "detail": "polygon price entitlement is NOT_AUTHORIZED on current key; using yfinance",
            },
            "llm": {
                "status": "ok" if CONFIG.has_llm else "unavailable",
                "detail": "local inference only" if not CONFIG.has_llm else "cloud key configured",
            },
            "telegram": {
                "status": "ok" if (TRAX.telegram_bot_token and TRAX.telegram_chat_id)
                           else "unconfigured",
            },
        },
        "session": session_status().__dict__,
    }
