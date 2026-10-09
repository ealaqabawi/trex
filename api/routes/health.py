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

    # Two real probes: SPY exercises the equity-options path (yfinance
    # primary), SPX exercises the index path (Tradier / MarketData.app).
    equity_probe = get_options_chain("SPY")
    index_probe = get_options_chain("SPX")

    return {
        "ok": True,
        "now_utc": now,
        "version": "0.1.0",
        "mode": TRAX.mode,
        "subsystems": {
            "options_feed": {
                "status": "ok" if equity_probe.ok else "degraded",
                "source": equity_probe.source or "unknown",
                "error": equity_probe.error if not equity_probe.ok else None,
            },
            "index_options_feed": {
                "status": "ok" if index_probe.ok else (
                    "unconfigured" if not (CONFIG.tradier_api_key or CONFIG.marketdata_app_token)
                    else "degraded"
                ),
                "source": index_probe.source or "none",
                "error": index_probe.error if not index_probe.ok else None,
                "detail": "SPX / NDX / RUT need TRADIER_API_KEY or MARKETDATA_APP_TOKEN",
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
