"""API smoke tests via FastAPI's TestClient.

These do NOT verify yfinance connectivity; the goal is that every route
responds and returns the documented shape even when upstream feeds are
unavailable.
"""

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_health_responds():
    r = client.get("/api/v1/health/")
    assert r.status_code == 200
    body = r.json()
    assert "subsystems" in body
    assert "session" in body
    assert body["mode"] in ("research", "paper", "live-disabled")


def test_agents_catalog():
    r = client.get("/api/v1/agents/catalog")
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert any(a["id"] == "options_analyst" for a in agents)


def test_risk_envelope_returns():
    r = client.get("/api/v1/risk/")
    assert r.status_code == 200
    body = r.json()
    assert body["live_execution"]["enabled"] is False
    assert body["envelope"]["max_concurrent_positions"] > 0


def test_settings_read_only():
    r = client.get("/api/v1/settings/")
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert "SPY" in cfg["universe"] or len(cfg["universe"]) > 0


def test_mode_change_denied_without_write_flag(monkeypatch):
    monkeypatch.delenv("TRAX_ALLOW_SETTINGS_WRITE", raising=False)
    r = client.post("/api/v1/settings/mode", json={"mode": "paper"})
    assert r.status_code == 403


def test_mode_change_rejects_live():
    r = client.post("/api/v1/settings/mode", json={"mode": "live"})
    assert r.status_code == 403


def test_mode_change_rejects_bogus():
    r = client.post("/api/v1/settings/mode", json={"mode": "banana"})
    assert r.status_code == 400


def test_strategy_catalog():
    r = client.get("/api/v1/strategy/strategies")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["strategies"]]
    assert "momentum" in names
    assert "mean_reversion" in names
    assert "breakout" in names


def test_intelligence_sources_lists_statuses():
    r = client.get("/api/v1/intelligence/sources")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert any(s["id"] == "news" and s["status"] == "adapter required" for s in sources)
