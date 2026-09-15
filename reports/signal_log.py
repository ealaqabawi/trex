"""
Feedback / learning loop for published signals.

Every signal that goes out is logged. Later, `review_pending()` walks back
over signals old enough to have resolved and asks the only question that
matters: did price reach TP1 before it reached the stop? The resulting
hit-rate feeds straight back into scoring.py, so confidence is anchored to
what actually happened rather than to how good the setup looked.

Signals are only scored once resolved. An unresolved signal counts for
nothing — no credit for open positions.
"""

import json
import os
from datetime import datetime, timezone, timedelta

from utils.logger import get_logger

log = get_logger("signal_log")

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
SIGNAL_LOG = os.path.join(LOG_DIR, "signals.jsonl")
MIN_REVIEW_AGE_DAYS = 1
HIT_RATE_WINDOW = 20


def _ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def log_signal(signal: dict) -> None:
    """Append a published signal. Only actionable signals are worth logging —
    a HOLD has no levels to resolve against.

    Deduplicated per ticker/direction/day: the endpoint may be called many
    times in a session, and counting the same setup twice would skew the
    hit-rate that feeds back into scoring."""
    if signal.get("direction") not in ("LONG", "SHORT"):
        return

    today = signal.get("generated_at", "")[:10]
    for existing in load_signals():
        if (existing.get("ticker") == signal.get("ticker")
                and existing.get("direction") == signal.get("direction")
                and str(existing.get("generated_at", ""))[:10] == today):
            return

    _ensure_dir()
    record = dict(signal)
    record["outcome"] = None          # filled in by review_pending()
    record["resolved_at"] = None
    with open(SIGNAL_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    log.info("Logged %s %s signal for review", signal.get("ticker"), signal.get("direction"))


def load_signals() -> list[dict]:
    if not os.path.exists(SIGNAL_LOG):
        return []
    out = []
    with open(SIGNAL_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _save_all(signals: list[dict]) -> None:
    _ensure_dir()
    with open(SIGNAL_LOG, "w") as f:
        for s in signals:
            f.write(json.dumps(s, default=str) + "\n")


def recent_hit_rate(window: int = HIT_RATE_WINDOW) -> float | None:
    """Realised win rate over the most recent resolved signals, or None when
    there is no resolved history yet — scoring treats None as neutral rather
    than assuming success."""
    resolved = [s for s in load_signals() if s.get("outcome") in ("win", "loss")]
    if not resolved:
        return None
    recent = resolved[-window:]
    wins = sum(1 for s in recent if s["outcome"] == "win")
    return wins / len(recent)


def review_pending() -> dict:
    """Resolve signals old enough to have played out, using subsequent daily
    bars. TP1 before stop = win; stop first = loss; neither = expired."""
    from data.historical import get_historical_bars

    signals = load_signals()
    now = datetime.now(timezone.utc)
    reviewed = {"win": 0, "loss": 0, "expired": 0, "skipped": 0}

    for sig in signals:
        if sig.get("outcome") is not None or not sig.get("levels"):
            continue
        try:
            issued = datetime.fromisoformat(sig["generated_at"])
        except (KeyError, ValueError):
            reviewed["skipped"] += 1
            continue
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        if now - issued < timedelta(days=MIN_REVIEW_AGE_DAYS):
            reviewed["skipped"] += 1
            continue

        hist = get_historical_bars(sig["ticker"], period="3mo")
        if not hist.ok:
            reviewed["skipped"] += 1
            continue

        after = [b for b in hist.bars if b.date >= issued.date().isoformat()]
        if not after:
            reviewed["skipped"] += 1
            continue

        L = sig["levels"]
        outcome = "expired"
        for bar in after:
            if sig["direction"] == "LONG":
                if bar.low <= L["stop_loss"]:
                    outcome = "loss"; break
                if bar.high >= L["tp1"]:
                    outcome = "win"; break
            else:
                if bar.high >= L["stop_loss"]:
                    outcome = "loss"; break
                if bar.low <= L["tp1"]:
                    outcome = "win"; break

        sig["outcome"] = outcome
        sig["resolved_at"] = now.isoformat(timespec="seconds")
        reviewed[outcome] += 1

    _save_all(signals)
    return reviewed


if __name__ == "__main__":
    result = review_pending()
    rate = recent_hit_rate()
    print("reviewed:", result)
    print("hit rate:", f"{rate:.0%}" if rate is not None else "no resolved history yet")
