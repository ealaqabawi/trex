"""Alert channels — Slack webhook, Discord webhook, and the Telegram
Bot API. All three are opt-in and no-op cleanly if their credentials
are missing, so alerting never becomes a hard dependency.

Telegram is a FIRST-PARTY channel (not just a webhook): the user owns
their bot (via @BotFather) and their chat. send_telegram_alert posts
to https://api.telegram.org/bot<token>/sendMessage with the configured
chat_id. No third-party platform is scraped, no credentials are
captured — the token is read from env and never leaks into logs or
responses.
"""

import time
from typing import Optional

import requests

from utils.config import CONFIG
from utils.logger import get_logger
from utils.trax_config import TRAX

log = get_logger("alerts")

TELEGRAM_BASE = "https://api.telegram.org"
TELEGRAM_TIMEOUT = 10

# Health probe caches getMe for a minute so /api/v1/health doesn't hit
# api.telegram.org on every poll.
_VERIFY_CACHE: dict = {"ts": 0.0, "result": None}
_VERIFY_TTL = 60.0


def send_slack_alert(message: str) -> bool:
    if not CONFIG.__dict__.get("slack_webhook_url"):
        return False
    try:
        resp = requests.post(CONFIG.__dict__["slack_webhook_url"], json={"text": message}, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Slack alert failed: %s", e)
        return False


def send_discord_alert(message: str) -> bool:
    if not CONFIG.__dict__.get("discord_webhook_url"):
        return False
    try:
        resp = requests.post(CONFIG.__dict__["discord_webhook_url"], json={"content": message}, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Discord alert failed: %s", e)
        return False


def _redact_token_in(text: str) -> str:
    """Make sure the bot token never surfaces in error messages or logs.
    Tokens follow the pattern <digits>:<35+ alphanumeric>; we replace the
    whole segment after /bot in URLs plus any literal occurrence."""
    token = TRAX.telegram_bot_token
    if not token:
        return text
    return str(text).replace(token, "[redacted]")


def telegram_get_me(force_refresh: bool = False) -> dict:
    """Call Telegram's getMe to confirm the configured token is valid.
    Returns {ok, bot_id, username, error}. Cached for 60s to avoid
    spamming the Bot API from /api/v1/health polling."""
    if not TRAX.telegram_bot_token:
        return {"ok": False, "error": "not_configured",
                "detail": "TELEGRAM_BOT_TOKEN is not set"}

    now = time.time()
    if not force_refresh and _VERIFY_CACHE["result"] is not None:
        if now - _VERIFY_CACHE["ts"] < _VERIFY_TTL:
            return _VERIFY_CACHE["result"]

    url = f"{TELEGRAM_BASE}/bot{TRAX.telegram_bot_token}/getMe"
    try:
        resp = requests.get(url, timeout=TELEGRAM_TIMEOUT)
        if resp.status_code == 401:
            result = {"ok": False, "error": "invalid_token",
                      "detail": "Telegram rejected the bot token (401)"}
        elif resp.ok and resp.json().get("ok"):
            r = resp.json()["result"]
            result = {"ok": True, "bot_id": r.get("id"),
                      "username": r.get("username"),
                      "first_name": r.get("first_name")}
        else:
            result = {"ok": False, "error": "api_error",
                      "detail": _redact_token_in(
                          f"status={resp.status_code} body={resp.text[:200]}")}
    except requests.RequestException as e:
        result = {"ok": False, "error": "network_error",
                  "detail": _redact_token_in(str(e))}

    _VERIFY_CACHE["ts"] = now
    _VERIFY_CACHE["result"] = result
    return result


def send_telegram_alert(
    text: str,
    parse_mode: str = "Markdown",
    disable_web_page_preview: bool = True,
    chat_id: Optional[str] = None,
) -> dict:
    """Post a message to the configured Telegram chat via the Bot API.
    Returns {ok, status_code, error, response}. Always logs the attempt
    to memory.telegram_history so the dashboard reflects reality.

    Returns {ok: False, error: 'not_configured'} without raising when
    the token or chat id is missing, so callers can safely invoke this
    without pre-checking config."""
    effective_chat = chat_id or TRAX.telegram_chat_id

    if not TRAX.telegram_bot_token or not effective_chat:
        result = {
            "ok": False, "status_code": 0, "error": "not_configured",
            "detail": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set",
            "response": None,
        }
        _log_delivery(text=text, result=result, chat_id=effective_chat)
        return result

    url = f"{TELEGRAM_BASE}/bot{TRAX.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": effective_chat,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }

    try:
        resp = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:500]}
        if resp.ok and body.get("ok"):
            result = {
                "ok": True, "status_code": resp.status_code,
                "error": None, "response": body.get("result"),
            }
        else:
            # Telegram returns 400 with {"ok":false,"description":"..."}
            # — surface the description, redacted.
            desc = body.get("description") if isinstance(body, dict) else None
            result = {
                "ok": False, "status_code": resp.status_code,
                "error": "api_error",
                "detail": _redact_token_in(desc or str(body)[:200]),
                "response": body,
            }
    except requests.RequestException as e:
        result = {
            "ok": False, "status_code": 0, "error": "network_error",
            "detail": _redact_token_in(str(e)), "response": None,
        }

    _log_delivery(text=text, result=result, chat_id=effective_chat)
    return result


def _log_delivery(text: str, result: dict, chat_id: Optional[str]) -> None:
    """Record this attempt in memory.telegram_history. Never let a logging
    failure propagate — delivery success must not depend on the DB."""
    try:
        # Imported lazily so this module stays usable even in tests that
        # patch the memory layer.
        from memory.repository import record_telegram
        record_telegram(
            body=text,
            delivered=bool(result.get("ok")),
            chat_id=chat_id,
            error=result.get("error") if not result.get("ok") else None,
        )
    except Exception as e:  # noqa: BLE001
        log.error("failed to log Telegram delivery: %s",
                  _redact_token_in(str(e)))


def send_alert(message: str) -> None:
    """Fan out to every configured channel; silently no-ops if none are set.
    Telegram is included: a `send_alert` call delivers to Slack, Discord,
    AND Telegram when they're each configured."""
    sent_any = False
    sent_any |= send_slack_alert(message)
    sent_any |= send_discord_alert(message)
    if TRAX.telegram_bot_token and TRAX.telegram_chat_id:
        sent_any |= bool(send_telegram_alert(message).get("ok"))
    if not sent_any:
        log.info("No alert channel configured — alert not sent: %s", message)
