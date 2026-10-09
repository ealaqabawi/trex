"""
Trex forward-test journal: every alert the n8n scanner sends is logged here, and review() checks
each one against later Capital.com candles to see whether the target or the stop was hit first.
Analysis only - nothing here trades. Journal: ~/trex/logs/trex_alerts.jsonl
"""
import json
import time
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent.parent / "logs" / "trex_alerts.jsonl"


def log_alert(a: dict) -> dict:
    if not a.get("signal"):
        return {"skipped": "not a trade alert"}
    rec = {k: a.get(k) for k in ("signal", "ticker", "name", "price", "sl", "tp", "time", "source", "verdict", "spread")}
    rec["logged_at"] = int(time.time())
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _alerts():
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def review(candles_fn, days: float = 30) -> dict:
    """candles_fn(symbol) -> Yahoo-shape chart dict. Returns per-alert outcome and totals in R."""
    since = time.time() - days * 86400
    alerts = [a for a in _alerts() if (a.get("logged_at") or 0) >= since]
    cache, rows = {}, []
    for a in alerts:
        sym = a.get("ticker")
        try:
            price, sl, tp = float(a["price"]), float(a["sl"]), float(a["tp"])
        except (TypeError, ValueError, KeyError):
            continue
        if sym not in cache:
            try:
                cache[sym] = candles_fn(sym)["chart"]["result"][0]
            except Exception as e:  # noqa: BLE001
                cache[sym] = {"error": str(e)}
        res = cache[sym]
        outcome, r = "OPEN", None
        if "timestamp" in res:
            q = res["indicators"]["quote"][0]
            buy = str(a.get("signal")).upper() == "BUY"
            risk = abs(price - sl) or 1e-12
            for t, h, l in zip(res["timestamp"], q["high"], q["low"]):
                if t < a["logged_at"] - 300 or h is None:
                    continue
                hit_sl = (l <= sl) if buy else (h >= sl)
                hit_tp = (h >= tp) if buy else (l <= tp)
                if hit_sl:  # stop counts first if both are inside one candle (conservative)
                    outcome, r = "STOP", -1.0
                    break
                if hit_tp:
                    outcome, r = "TARGET", round(abs(tp - price) / risk, 2)
                    break
            if outcome == "OPEN" and a["logged_at"] < time.time() - 3.4 * 86400:
                outcome = "UNKNOWN (older than the ~3.5 days of Capital.com 5m history)"
        rows.append(dict(a, outcome=outcome, r=r))
    done = [x for x in rows if x["r"] is not None]
    per = {}
    for x in done:
        p = per.setdefault(x.get("name") or x.get("ticker"), {"trades": 0, "wins": 0, "R": 0.0})
        p["trades"] += 1
        p["wins"] += x["r"] > 0
        p["R"] = round(p["R"] + x["r"], 2)
    return {"alerts": len(rows), "closed": len(done), "open": sum(1 for x in rows if x["outcome"] == "OPEN"),
            "wins": sum(1 for x in done if x["r"] > 0), "total_R": round(sum(x["r"] for x in done), 2),
            "by_market": per, "recent": rows[-20:],
            "note": "R before spread; stop assumed first when both levels are inside one candle."}
