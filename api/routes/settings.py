"""Settings & integrations — exposes the TRAX config surface.

Secrets are never serialised, only booleans indicating whether a
credential is present. Writing new values requires `TRAX_ALLOW_SETTINGS_WRITE`
to be explicitly enabled; otherwise this endpoint is read-only.
"""

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.trax_config import TRAX, ALLOWED_MODES
from memory.repository import set_state, get_state

router = APIRouter()


@router.get("/")
def settings():
    return {
        "ok": True,
        "config": TRAX.to_dict(),
        "overrides": {
            "mode": get_state("mode"),
        },
    }


class ModeChange(BaseModel):
    mode: str


@router.post("/mode")
def set_mode(payload: ModeChange):
    mode = payload.mode.strip().lower()

    # Reject live-execution explicitly BEFORE the allowed-list check, so the
    # error message tells the caller why instead of just "invalid mode".
    if mode in ("live", "live-execution"):
        raise HTTPException(status_code=403,
                              detail="live execution is not available from this surface")

    if mode not in ALLOWED_MODES:
        raise HTTPException(status_code=400,
                              detail=f"invalid mode; allowed: {list(ALLOWED_MODES)}")

    if os.getenv("TRAX_ALLOW_SETTINGS_WRITE", "false").lower() != "true":
        raise HTTPException(status_code=403,
                              detail="settings are read-only; set TRAX_ALLOW_SETTINGS_WRITE=true to permit runtime mode changes")

    set_state("mode", mode)
    return {"ok": True, "mode": mode,
            "note": "runtime override saved; process restart still reads TRAX_MODE from env"}
