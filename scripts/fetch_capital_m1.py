#!/usr/bin/env python3
"""
Download Capital.com 1-minute or 5-minute history (bid OHLC + spread) for the MT5 Strategy Tester.

Read-only: it uses the same GET-only client as the Trex price server (service/capital_feed.py).
Output: data/cache/capital_m1/<EPIC>_<M1|M5>.csv.gz with columns
    time_utc,open,high,low,close,spread,volume
where open..close are BID prices (MT5 charts are bid based) and spread = ask - bid at the bar close.

Resumable: progress is kept in <EPIC>_<res>.part.csv.gz and the run stops cleanly after --budget seconds,
so it can be called repeatedly until it prints ALL DONE.

Usage:
    python3 scripts/fetch_capital_m1.py --res M5 --workers 4 --from 2025-10-01 --to 2026-10-01 --budget 160 GOLD US100 ...
"""
import argparse
import gzip
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
sys.path.insert(0, str(ROOT / "service"))
import capital_feed as cf  # noqa: E402

DEFAULT = ["GOLD", "US100", "OIL_CRUDE", "BTCUSD", "ETHUSD", "GBPUSD", "EURUSD", "USDCAD",
           "USDCHF", "DE40", "OIL_BRENT", "COPPER"]
HEADER = "time_utc,open,high,low,close,spread,volume\n"
RES = {"M1": ("MINUTE", 1), "M5": ("MINUTE_5", 5)}
_tls = threading.local()


def client():
    """One Capital.com session per worker thread (each client serialises its own requests)."""
    if not hasattr(_tls, "c"):
        _tls.c = cf.CapitalClient()
    return _tls.c


def fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def utc(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def last_time(part):
    """Timestamp of the last complete row in a partial file (None if empty)."""
    if not part.exists():
        return None
    last = None
    try:
        with gzip.open(part, "rt") as f:
            for row in f:
                if row[:1].isdigit() and row.endswith("\n"):
                    last = row
    except (EOFError, OSError):
        pass  # an interrupted write leaves a truncated gzip member; rows before it are kept
    return datetime.fromtimestamp(int(last.split(",")[0]), tz=timezone.utc) if last else None


def fetch(epic, start, end, out_dir, deadline, res="M1"):
    """Returns True when the market is complete, False when the time budget ran out."""
    resolution, step = RES[res]
    part = out_dir / f"{epic}_{res}.part.csv.gz"
    lt = last_time(part)
    if lt is None:
        with gzip.open(part, "wt") as f:
            f.write(HEADER)
        cur = start
    else:
        cur = lt + timedelta(minutes=step)
    with gzip.open(part, "at") as f:
        while cur < end:
            if time.time() > deadline:
                return False
            try:
                j = client().get(f"/api/v1/prices/{epic}", {"resolution": resolution, "max": 1000, "from": fmt(cur)})
            except cf.CapitalError as e:
                msg = str(e)
                if "429" in msg:
                    time.sleep(2)
                    continue
                if "404" in msg or "not-found" in msg:
                    cur += timedelta(days=1)  # no data in this window (holiday): jump a day
                    continue
                raise
            prices = j.get("prices") or []
            if not prices:
                cur += timedelta(days=1)
                continue
            rows = []
            for p in prices:
                t = utc(p["snapshotTimeUTC"])
                if t < cur:
                    continue
                if t >= end:
                    break
                o, h, l, c = p["openPrice"], p["highPrice"], p["lowPrice"], p["closePrice"]
                if None in (o.get("bid"), h.get("bid"), l.get("bid"), c.get("bid")):
                    continue
                spr = (c.get("ask") or c["bid"]) - c["bid"]
                rows.append(f"{int(t.timestamp())},{o['bid']},{h['bid']},{l['bid']},{c['bid']},{spr:.6g},{int(p.get('lastTradedVolume') or 0)}\n")
            f.write("".join(rows))
            cur = max(utc(prices[-1]["snapshotTimeUTC"]) + timedelta(minutes=step), cur + timedelta(minutes=step))
            time.sleep(0.11)  # Capital.com allows 10 requests per second
    part.rename(out_dir / f"{epic}_{res}.csv.gz")
    return True


def run_one(epic, start, end, out_dir, deadline, res):
    if (out_dir / f"{epic}_{res}.csv.gz").exists():
        return f"{epic}: complete"
    try:
        if not fetch(epic, start, end, out_dir, deadline, res):
            return f"{epic}: paused at {last_time(out_dir / f'{epic}_{res}.part.csv.gz')} - run again to resume"
        return f"{epic}: complete"
    except Exception as e:  # noqa: BLE001
        return f"{epic}: FAILED {str(e)[:200]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2025-10-01")
    ap.add_argument("--to", dest="end", default="2026-10-01")
    ap.add_argument("--res", default="M1", choices=sorted(RES))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--budget", type=float, default=1e9, help="stop after this many seconds (resume later)")
    ap.add_argument("epics", nargs="*")
    a = ap.parse_args()
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)
    deadline = time.time() + a.budget
    out_dir = ROOT / "data" / "cache" / "capital_m1"
    out_dir.mkdir(parents=True, exist_ok=True)
    epics = a.epics or DEFAULT
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        results = list(ex.map(lambda e: run_one(e, start, end, out_dir, deadline, a.res), epics))
    for r in results:
        print(r, flush=True)
    if all(r.endswith("complete") for r in results):
        print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
