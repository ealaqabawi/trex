"""Telegram sender + API routes.

Mocks requests to avoid hitting api.telegram.org during unit tests.
Verifies: URL/body shape, success + failure paths, record_telegram
logging, not_configured short-circuit, token redaction, writes-gating.
"""

import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from utils import alerts as alerts_module
from utils.alerts import send_telegram_alert, telegram_get_me


client = TestClient(app)


FAKE_TOKEN = "9999999999:AAFakeBotTokenForTestsThatIsNotRealAtAll"
FAKE_CHAT_ID = "123456789"


@pytest.fixture(autouse=True)
def _reset_verify_cache():
    """Make sure the module-level getMe cache doesn't bleed between tests."""
    alerts_module._VERIFY_CACHE["ts"] = 0.0
    alerts_module._VERIFY_CACHE["result"] = None
    yield


class _FakeTrax:
    """Mimics the subset of utils.trax_config.TRAX that the Telegram code
    reads. The real TRAX is a frozen dataclass, so we swap the module-level
    reference instead of mutating the instance."""
    telegram_bot_token = FAKE_TOKEN
    telegram_chat_id = FAKE_CHAT_ID
    telegram_autosend = False
    # health.py uses TRAX.mode for the top-level mode field
    mode = "research"


@pytest.fixture
def configured(monkeypatch):
    """Replace the TRAX reference in every module the Telegram paths read
    from, so the sender sees configured credentials."""
    fake = _FakeTrax()
    from utils import alerts as alerts_module
    from api.routes import telegram as telegram_route
    from api.routes import health as health_route
    monkeypatch.setattr(alerts_module, "TRAX", fake)
    monkeypatch.setattr(telegram_route, "TRAX", fake)
    monkeypatch.setattr(health_route, "TRAX", fake)
    yield fake


def _ok_response(payload):
    r = MagicMock()
    r.ok = True
    r.status_code = 200
    r.json.return_value = payload
    return r


def _err_response(status, payload=None):
    r = MagicMock()
    r.ok = False
    r.status_code = status
    r.json.return_value = payload or {"ok": False, "description": "nope"}
    r.text = str(payload)
    return r


# --- send_telegram_alert ---------------------------------------------------

def test_send_not_configured_short_circuits():
    """With no token/chat, the sender returns an error without raising
    and without touching the network."""
    with patch("utils.alerts.requests.post") as mock_post:
        result = send_telegram_alert("hello")
    assert result["ok"] is False
    assert result["error"] == "not_configured"
    mock_post.assert_not_called()


def test_send_hits_correct_url_and_logs_delivery(configured):
    with patch("utils.alerts.requests.post",
                return_value=_ok_response({"ok": True, "result": {"message_id": 42}})) as mock_post, \
         patch("memory.repository.record_telegram") as mock_log:
        result = send_telegram_alert("hello world")

    mock_post.assert_called_once()
    url, = mock_post.call_args.args
    assert url == f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"

    payload = mock_post.call_args.kwargs["json"]
    assert payload["chat_id"] == FAKE_CHAT_ID
    assert payload["text"] == "hello world"
    assert payload["parse_mode"] == "Markdown"
    assert payload["disable_web_page_preview"] is True

    assert result["ok"] is True
    assert result["status_code"] == 200
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["delivered"] is True


def test_send_failure_logs_with_delivered_false(configured):
    with patch("utils.alerts.requests.post",
                return_value=_err_response(400, {"ok": False, "description": "chat not found"})), \
         patch("memory.repository.record_telegram") as mock_log:
        result = send_telegram_alert("hello")

    assert result["ok"] is False
    assert result["error"] == "api_error"
    assert "chat not found" in (result["detail"] or "")
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["delivered"] is False


def test_send_redacts_token_in_error_message(configured):
    """A requests exception that happens to echo the URL (containing the
    token) must have the token stripped before it reaches logs or the
    client response."""
    import requests
    err = requests.ConnectionError(
        f"HTTPSConnectionPool(host='api.telegram.org', port=443): "
        f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage"
    )
    with patch("utils.alerts.requests.post", side_effect=err):
        result = send_telegram_alert("hello")
    assert result["ok"] is False
    assert FAKE_TOKEN not in (result["detail"] or "")
    assert "[redacted]" in (result["detail"] or "")


def test_logging_failure_doesnt_break_delivery(configured):
    """A broken memory DB must never make a successful send look failed."""
    with patch("utils.alerts.requests.post",
                return_value=_ok_response({"ok": True, "result": {"message_id": 1}})), \
         patch("memory.repository.record_telegram",
                side_effect=RuntimeError("db offline")):
        result = send_telegram_alert("hello")
    assert result["ok"] is True


# --- telegram_get_me -------------------------------------------------------

def test_get_me_not_configured():
    result = telegram_get_me(force_refresh=True)
    assert result["ok"] is False
    assert result["error"] == "not_configured"


def test_get_me_success(configured):
    with patch("utils.alerts.requests.get",
                return_value=_ok_response({"ok": True, "result": {
                    "id": 777, "username": "trex_bot", "first_name": "TRAX"
                }})):
        result = telegram_get_me(force_refresh=True)
    assert result["ok"] is True
    assert result["username"] == "trex_bot"
    assert result["bot_id"] == 777


def test_get_me_invalid_token_returns_401(configured):
    with patch("utils.alerts.requests.get", return_value=_err_response(401)):
        result = telegram_get_me(force_refresh=True)
    assert result["ok"] is False
    assert result["error"] == "invalid_token"


def test_get_me_cached_within_ttl(configured):
    """Second call within the TTL window must NOT hit the network."""
    with patch("utils.alerts.requests.get",
                return_value=_ok_response({"ok": True, "result": {
                    "id": 1, "username": "cached", "first_name": "x",
                }})) as mock_get:
        telegram_get_me(force_refresh=True)
        telegram_get_me()  # should hit cache
    assert mock_get.call_count == 1


# --- API routes ------------------------------------------------------------

def test_route_verify_hits_telegram(configured, monkeypatch):
    monkeypatch.setenv("TRAX_ALLOW_SETTINGS_WRITE", "false")
    with patch("utils.alerts.requests.get",
                return_value=_ok_response({"ok": True, "result": {
                    "id": 1, "username": "trex_bot", "first_name": "x",
                }})):
        r = client.get("/api/v1/telegram/verify")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["username"] == "trex_bot"


def test_route_test_requires_write_flag(configured, monkeypatch):
    monkeypatch.delenv("TRAX_ALLOW_SETTINGS_WRITE", raising=False)
    r = client.post("/api/v1/telegram/test", json={})
    assert r.status_code == 403


def test_route_test_sends_with_write_flag(configured, monkeypatch):
    monkeypatch.setenv("TRAX_ALLOW_SETTINGS_WRITE", "true")
    with patch("utils.alerts.requests.post",
                return_value=_ok_response({"ok": True, "result": {"message_id": 7}})):
        r = client.post("/api/v1/telegram/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # Token must never appear in the API response.
    assert FAKE_TOKEN not in r.text


def test_route_send_rejects_empty_text(configured, monkeypatch):
    monkeypatch.setenv("TRAX_ALLOW_SETTINGS_WRITE", "true")
    r = client.post("/api/v1/telegram/send", json={"text": "   "})
    assert r.status_code == 400


def test_route_telegram_summary_includes_verify(configured):
    with patch("utils.alerts.requests.get",
                return_value=_ok_response({"ok": True, "result": {
                    "id": 1, "username": "trex_bot", "first_name": "x",
                }})):
        r = client.get("/api/v1/telegram/")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["verify"]["ok"] is True
    assert body["verify"]["username"] == "trex_bot"


def test_health_telegram_reports_invalid_token(configured):
    with patch("utils.alerts.requests.get", return_value=_err_response(401)):
        r = client.get("/api/v1/health/")
    assert r.status_code == 200
    body = r.json()
    assert body["subsystems"]["telegram"]["status"] == "invalid_token"


def test_health_telegram_unconfigured_without_env():
    # No `configured` fixture → env vars empty by default
    r = client.get("/api/v1/health/")
    assert r.status_code == 200
    assert r.json()["subsystems"]["telegram"]["status"] == "unconfigured"
