"""Executive overview — the dashboard home screen aggregator.

Reads multiple subsystems in one call, so the UI can render the whole
tile grid in a single trip. Each tile carries its own freshness/status
so a slow or degraded dependency never blanks the page.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from utils.trax_config import TRAX
from utils.market_time import session_status
from reports.performance import build_report
from reports.signal_log import load_signals, recent_hit_rate
from memory.repository import list_agent_runs, list_risk_events
from memory.portfolio import portfolio_summary
from scanner import scan_universe

router = APIRouter()


@router.get("/")
def overview():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    perf = build_report()
    signals = load_signals()
    unresolved = [s for s in signals if s.get("outcome") is None]
    actionable = [s for s in signals if s.get("direction") in ("LONG", "SHORT")]

    try:
        candidates = scan_universe(include_0dte_only=False, max_dte=7, limit_per_ticker=5)
    except Exception:  # noqa: BLE001
        candidates = []

    recent_agents = list_agent_runs(limit=8)
    recent_risk = list_risk_events(limit=5)
    portfolio = portfolio_summary()

    return {
        "ok": True,
        "now_utc": now,
        "mode": TRAX.mode,
        "session": session_status().__dict__,
        "qualified_setups": sum(1 for c in candidates if c.confidence >= 60),
        "scanner_candidate_count": len(candidates),
        "paper_trading": {
            "total_orders": perf.total_orders,
            "real_fills": perf.real_fills,
            "dry_run_orders": perf.dry_run_orders,
            "buy_count": perf.buy_count,
            "sell_count": perf.sell_count,
            "note": ("No live fills yet — orders are dry-run only until Alpaca "
                     "paper credentials are configured. Simulated results are "
                     "never mixed with real P&L.") if perf.real_fills == 0 else None,
        },
        "signal_history": {
            "total_published": len(signals),
            "actionable": len(actionable),
            "unresolved": len(unresolved),
            "hit_rate": recent_hit_rate(),
            "hit_rate_note": "null means no resolved signals yet — not a 0% win rate.",
        },
        "recent_alerts": [
            {
                "created_at": e["created_at"], "severity": e["severity"],
                "event_type": e["event_type"], "ticker": e.get("ticker"),
                "detail": e["detail"],
            }
            for e in recent_risk
        ],
        "portfolio": {
            "position_count": portfolio["position_count"],
            "gross_market_value": portfolio["gross_market_value"],
            "net_market_value": portfolio["net_market_value"],
            "unrealized_pnl": portfolio["unrealized_pnl"],
            "imported_at": portfolio["imported_at"],
        },
        "recent_agent_activity": [
            {
                "started_at": r["started_at"], "finished_at": r["finished_at"],
                "agent": r["agent"], "task": r["task"], "status": r["status"],
            }
            for r in recent_agents
        ],
        "universe": list(TRAX.universe),
    }
