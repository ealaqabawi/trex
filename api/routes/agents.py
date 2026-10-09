"""Agent activity monitor."""

from fastapi import APIRouter

from memory.repository import list_agent_runs, start_agent_run, finish_agent_run

router = APIRouter()


@router.get("/")
def agents(limit: int = 50):
    runs = list_agent_runs(limit=limit)
    buckets: dict[str, int] = {}
    for r in runs:
        buckets[r["agent"]] = buckets.get(r["agent"], 0) + 1
    return {"ok": True, "runs": runs, "by_agent": buckets}


@router.get("/catalog")
def catalog():
    """Enumerates the TRAX agent roles. Each entry describes what the
    agent is *supposed* to do; whether a specific run has happened is
    answered by /api/v1/agents/ (the run log)."""
    return {
        "ok": True,
        "agents": [
            {"id": "orchestrator", "label": "Research Orchestrator",
             "role": "coordinates tasks, picks tools, combines validated results"},
            {"id": "market_intel", "label": "Market Intelligence",
             "role": "price action, volatility, scheduled events"},
            {"id": "options_analyst", "label": "Options Analyst",
             "role": "chain structure, Greeks, liquidity, premium economics"},
            {"id": "public_observer", "label": "Public Agent Observer",
             "role": "collects and evaluates publicly posted trader & AI predictions"},
            {"id": "strategy_researcher", "label": "Strategy Researcher",
             "role": "formulates hypotheses to test"},
            {"id": "backtester", "label": "Backtesting & Evaluation",
             "role": "reproducible historical tests, metrics, weaknesses"},
            {"id": "risk_analyst", "label": "Risk Analyst",
             "role": "max loss, sizing, portfolio exposure, risk limits"},
            {"id": "signal_publisher", "label": "Signal Publisher",
             "role": "renders validated findings into Telegram-ready signals"},
            {"id": "performance_auditor", "label": "Performance Auditor",
             "role": "compares published predictions with later market outcomes"},
        ],
    }
