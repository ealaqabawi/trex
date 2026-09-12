"""
ExecutionAgent — Phase 8. Places orders against Alpaca's PAPER trading API
only. This module hard-refuses to talk to a live-money endpoint, and
defaults to DRY_RUN (logs the order it would place, sends nothing) unless
both Alpaca credentials are configured AND DRY_RUN is explicitly disabled.

This is the only agent in T-REX with any order-placing capability, and it is
scoped to paper trading on purpose. Extending this to real money is a
deliberate decision to make directly with your broker, not something to
flip on here.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

from agents.risk_agent import OrderProposal
from utils.config import CONFIG
from utils.logger import get_logger

log = get_logger("execution_agent")

ALLOWED_HOST_FRAGMENT = "paper-api.alpaca.markets"
ORDER_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "orders.jsonl"
)


@dataclass
class ExecutionResult:
    submitted: bool
    dry_run: bool
    ticker: str
    action: str
    shares: float
    detail: str


def _dry_run_enabled() -> bool:
    # Defaults to True (dry run) unless explicitly set to "false".
    return os.getenv("DRY_RUN", "true").strip().lower() != "false"


def _paper_endpoint_configured() -> bool:
    base_url = CONFIG.__dict__.get("alpaca_base_url") or os.getenv("ALPACA_BASE_URL", "")
    return ALLOWED_HOST_FRAGMENT in base_url


def _log_order(result: ExecutionResult, price: Optional[float] = None) -> None:
    """Append every attempted order (dry-run included) to logs/orders.jsonl,
    so Phase 11's performance report has a real history to compute from even
    before live paper credentials exist."""
    os.makedirs(os.path.dirname(ORDER_LOG_PATH), exist_ok=True)
    record = {
        "timestamp": time.time(),
        "ticker": result.ticker,
        "action": result.action,
        "shares": result.shares,
        "price": price,
        "submitted": result.submitted,
        "dry_run": result.dry_run,
        "detail": result.detail,
    }
    with open(ORDER_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def execute_proposal(proposal: OrderProposal) -> ExecutionResult:
    if not proposal.approved or proposal.action not in ("BUY", "SELL"):
        result = ExecutionResult(
            submitted=False, dry_run=True, ticker=proposal.ticker,
            action=proposal.action, shares=0,
            detail=f"not executed — proposal not approved ({proposal.reasons})",
        )
        _log_order(result)
        return result

    shares = proposal.size.shares if proposal.size else 0.0
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if ALLOWED_HOST_FRAGMENT not in base_url:
        log.error(
            "ALPACA_BASE_URL (%s) is not the paper endpoint — refusing to place any order. "
            "T-REX's execution agent only supports paper trading.", base_url,
        )
        result = ExecutionResult(
            submitted=False, dry_run=True, ticker=proposal.ticker,
            action=proposal.action, shares=shares,
            detail="refused — ALPACA_BASE_URL is not the paper trading endpoint",
        )
        _log_order(result)
        return result

    api_key = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    dry_run = _dry_run_enabled() or not (api_key and api_secret)

    if dry_run:
        reason = "DRY_RUN mode" if _dry_run_enabled() else "no Alpaca credentials configured"
        log.info("[DRY RUN] Would place %s order: %.4f shares of %s (%s)",
                  proposal.action, shares, proposal.ticker, reason)
        price = proposal.size.dollar_amount / shares if (proposal.size and shares) else None
        result = ExecutionResult(
            submitted=False, dry_run=True, ticker=proposal.ticker,
            action=proposal.action, shares=shares, detail=f"dry run only ({reason})",
        )
        _log_order(result, price=price)
        return result

    order = {
        "symbol": proposal.ticker,
        "qty": round(shares, 4),
        "side": "buy" if proposal.action == "BUY" else "sell",
        "type": "market",
        "time_in_force": "day",
    }
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}

    try:
        resp = requests.post(f"{base_url}/v2/orders", json=order, headers=headers, timeout=10)
        resp.raise_for_status()
        log.info("Paper order submitted: %s", resp.json())
        result = ExecutionResult(
            submitted=True, dry_run=False, ticker=proposal.ticker,
            action=proposal.action, shares=shares, detail=str(resp.json()),
        )
        _log_order(result)
        return result
    except requests.RequestException as e:
        log.error("Paper order submission failed for %s: %s", proposal.ticker, e)
        result = ExecutionResult(
            submitted=False, dry_run=False, ticker=proposal.ticker,
            action=proposal.action, shares=shares, detail=f"error: {e}",
        )
        _log_order(result)
        return result
