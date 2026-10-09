"""Memory DB schema and repository round-trips."""

from memory.repository import (
    record_scanner_candidate, list_recent_candidates,
    start_agent_run, finish_agent_run, list_agent_runs,
    record_risk_event, list_risk_events,
    record_telegram, list_telegram_history,
    set_state, get_state,
    record_research_note, list_research_notes,
)


def test_scanner_candidate_round_trip():
    rid = record_scanner_candidate({
        "ticker": "SPY", "direction": "LONG", "contract_symbol": "SPY260101C00500000",
        "strike": 500.0, "expiration": "2026-01-01", "dte": 0, "mid": 1.25,
        "spread_pct": 0.05, "delta": 0.45, "implied_vol": 0.22, "volume": 1500,
        "open_interest": 2200, "confidence": 72, "rationale": "test", "raw": {"x": 1},
    })
    assert rid > 0
    rows = list_recent_candidates(limit=10, ticker="SPY")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "SPY"
    assert rows[0]["confidence"] == 72


def test_agent_run_lifecycle():
    run_id = start_agent_run("options_analyst", "scan SPY", model="llama3.2")
    finish_agent_run(run_id, "ok", "found 3 candidates", tokens=100)
    runs = list_agent_runs(limit=5)
    assert runs[0]["status"] == "ok"
    assert runs[0]["tokens"] == 100
    assert runs[0]["model"] == "llama3.2"


def test_risk_event_logging():
    record_risk_event("limit_breach", "warning", "position exceeded max",
                       ticker="NVDA", context={"attempted": 1500})
    events = list_risk_events()
    assert events[0]["event_type"] == "limit_breach"
    assert events[0]["ticker"] == "NVDA"


def test_telegram_history():
    record_telegram("hello world", delivered=True, ticker="SPY", direction="LONG")
    record_telegram("fail case", delivered=False, error="network down")
    rows = list_telegram_history()
    assert len(rows) == 2
    assert sum(r["delivered"] for r in rows) == 1


def test_system_state_upsert():
    set_state("mode", "research")
    assert get_state("mode") == "research"
    set_state("mode", "paper")
    assert get_state("mode") == "paper"
    assert get_state("nonexistent") is None


def test_research_notes():
    record_research_note("0DTE pin risk", "notes body", source="internal",
                          tags=["spx", "0dte"])
    notes = list_research_notes(topic="0DTE pin risk")
    assert len(notes) == 1
    assert "0dte" in (notes[0]["tags"] or "")
