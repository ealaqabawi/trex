"""
Phase 10 — daily digest + alerting.

Runs the Phase 9 supervisor pipeline across a watchlist, renders a plain-text
summary, writes it to logs/, and fires an alert (Slack/Discord, if
configured) when something needs a human's attention: an execution error, or
a SELL signal that actually executed (or would have, outside dry-run).
"""

import os
from datetime import datetime

from agents.supervisor import run_watchlist, PLACEHOLDER_EQUITY
from utils.alerts import send_alert
from utils.logger import get_logger

log = get_logger("daily_summary")

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def build_summary(watchlist: list[str], equity: float = PLACEHOLDER_EQUITY) -> str:
    outcomes = run_watchlist(watchlist, equity=equity)

    lines = [f"T-REX daily summary — {datetime.now().isoformat(timespec='seconds')}", ""]
    needs_attention = []

    for ticker, state in outcomes.items():
        execution = state["execution"]
        exec_line = "no order (HOLD or no proposal)"
        if execution is not None:
            exec_line = execution.detail
            if execution.action == "SELL" and (execution.submitted or execution.dry_run):
                needs_attention.append(f"{ticker}: SELL signal ({state['reason']})")
            if not execution.submitted and not execution.dry_run:
                needs_attention.append(f"{ticker}: execution error — {execution.detail}")

        lines.append(f"{ticker}: {state['signal']} | price={state['price']} | {state['reason']} | {exec_line}")

    summary = "\n".join(lines)

    report_path = os.path.join(REPORTS_DIR, f"daily_summary_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(report_path, "w") as f:
        f.write(summary + "\n")
    log.info("Daily summary written to %s", report_path)

    if needs_attention:
        alert_message = "T-REX alert:\n" + "\n".join(needs_attention)
        send_alert(alert_message)

    return summary


if __name__ == "__main__":
    import sys
    watchlist = sys.argv[1:] or ["AAPL", "NVDA", "SPY"]
    print(build_summary(watchlist))
