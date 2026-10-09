"""Risk Center — the independent risk engine's live state.

Mirrors the configured envelope (max premium, daily loss, concurrent
positions, etc.), the current utilization computed from the order log,
and the recent risk events written to the memory DB.
"""

from fastapi import APIRouter

from reports.performance import build_report
from reports.signal_log import load_signals
from risk.rules import RiskLimits
from memory.repository import list_risk_events
from utils.trax_config import TRAX

router = APIRouter()


@router.get("/")
def risk():
    env = TRAX.risk
    perf = build_report()
    signals = load_signals()
    open_signals = [s for s in signals if s.get("outcome") is None]

    legacy_limits = RiskLimits()

    return {
        "ok": True,
        "mode": TRAX.mode,
        "envelope": {
            "max_premium_per_position": env.max_premium_per_position,
            "max_daily_loss": env.max_daily_loss,
            "max_concurrent_positions": env.max_concurrent_positions,
            "max_spread_pct": env.max_spread_pct,
            "min_volume": env.min_volume,
            "min_open_interest": env.min_open_interest,
            "max_order_size": env.max_order_size,
        },
        "legacy_portfolio_limits": {
            "max_position_pct": legacy_limits.max_position_pct,
            "max_daily_loss_pct": legacy_limits.max_daily_loss_pct,
            "max_concurrent_positions": legacy_limits.max_concurrent_positions,
        },
        "utilization": {
            "open_signals": len(open_signals),
            "concurrent_position_utilization": (
                len(open_signals) / env.max_concurrent_positions
                if env.max_concurrent_positions else 0.0
            ),
            "real_fills": perf.real_fills,
            "dry_run_orders": perf.dry_run_orders,
        },
        "live_execution": {
            "enabled": False,
            "reason": "live execution is disabled by default — set TRAX_LIVE_UNLOCK and TRAX_MODE=paper first; live mode has no supported adapter",
            "unlock_token_present": TRAX.live_mode_unlock_present(),
        },
        "emergency_stop": {
            "active": TRAX.mode == "live-disabled",
            "detail": ("mode is 'live-disabled' — no new orders will leave this host"
                        if TRAX.mode == "live-disabled" else
                        "normal operation (no live orders can leave this host regardless)"),
        },
        "recent_events": list_risk_events(limit=20),
    }
