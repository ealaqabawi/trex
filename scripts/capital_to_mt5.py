#!/usr/bin/env python3
"""
Turn the Capital.com history cache (data/cache/capital_m1/<EPIC>_M5.csv.gz or _M1.csv.gz) into files the
MT5 script TrexImportCustom.mq5 loads as custom symbols (GOLD.cap, US100.cap, ...).

Each record is a raw MqlRates struct (60 bytes: time, open, high, low, close, tick_volume, spread, real_volume)
with BID prices and the real Capital.com spread in points, so the Strategy Tester charges the true cost.

Usage:
    python3 scripts/capital_to_mt5.py                 # writes into the Mac MT5 data folder if found
    python3 scripts/capital_to_mt5.py --out /some/MQL5/Files
Then in MT5: Navigator > Scripts > Trex > TrexImportCustom (drag onto any chart).
"""
import argparse
import gzip
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "capital_m1"
MAC_MT5 = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"


def convert(src: Path, out_dir: Path):
    epic = src.name.split("_M")[0]
    rows = [r.split(",") for r in gzip.open(src, "rt").read().splitlines()[1:] if r]
    digits = 0
    for r in rows[:5000]:
        for v in r[1:5]:
            if "." in v:
                digits = max(digits, len(v.split(".")[1]))
    point = 10 ** -digits
    recs, prev = [], 0
    for r in rows:
        t = int(r[0])
        o, h, l, c = map(float, r[1:5])
        if t <= prev:
            continue
        h, l = max(h, o, c), min(l, o, c)
        spread_pts = max(0, int(round(float(r[5]) / point)))
        recs.append(struct.pack("<qddddqiq", t, o, h, l, c, max(int(r[6]), 1), spread_pts, 0))
        prev = t
    (out_dir / f"{epic}.bin").write_bytes(b"".join(recs))
    return f"{epic}.cap,{digits},trex_import\\{epic}.bin,USD", len(recs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="MT5 MQL5/Files folder (default: the Mac MT5 app's folder)")
    ap.add_argument("--res", default="M5", choices=["M1", "M5"])
    a = ap.parse_args()
    base = Path(a.out) if a.out else MAC_MT5
    if not base.exists():
        raise SystemExit(f"MT5 Files folder not found: {base}\nInstall MT5 first or pass --out.")
    out_dir = base / "trex_import"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = []
    for src in sorted(CACHE.glob(f"*_{a.res}.csv.gz")):
        spec, n = convert(src, out_dir)
        specs.append(spec)
        print(f"{spec.split(',')[0]:14s} {n:7d} bars")
    (out_dir / "specs.csv").write_text("\n".join(specs) + "\n")
    print(f"Wrote {len(specs)} symbols to {out_dir}")


if __name__ == "__main__":
    main()
