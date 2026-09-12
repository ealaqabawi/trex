"""Slack/Discord webhook alerts — no-ops cleanly if no webhook URL is
configured, so alerting is opt-in rather than a hard dependency."""

import requests

from utils.config import CONFIG
from utils.logger import get_logger

log = get_logger("alerts")


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


def send_alert(message: str) -> None:
    """Fan out to every configured channel; silently no-ops if none are set."""
    sent = send_slack_alert(message) or send_discord_alert(message)
    if not sent:
        log.info("No alert webhook configured — alert not sent: %s", message)
