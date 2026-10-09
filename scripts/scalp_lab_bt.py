#!/usr/bin/env python3
"""
Trex Scalp Lab - Python twin of mt5/TrexScalpLab.mq5 v1.10 (same rules, same numbers expected).

Bar-for-bar port (MT5 Strategy Tester semantics, "1 minute OHLC"
on M5 bars): signals on the closed bar r[1], entry at the open of the next bar (buy at ask = bid + spread,
sell at bid), exits checked on each closed bar (gap fill at the open, stop before target inside a bar).
Indicators follow MT5's built-ins: ATR = SMA of true range, RSI = Wilder, EMA seeded with first price.
All times are UTC (the Capital.com cache is stored in UTC). Research only - it never places orders.

Usage:
    python3 scripts/fetch_capital_m1.py --res M5 --workers 12 --budget 150    # repeat until ALL DONE
    .venv/bin/python scripts/scalp_lab_bt.py                       # all markets in data/cache/capital_m1
    .venv/bin/python scripts/scalp_lab_bt.py --report reports/scalp_lab.md GOLD US100
"""
import gzip
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import numpy as np

NAMES = ["ALL", "TREX_SWEEP", "ORB", "RSI2", "EMA_PULLBACK", "AMD", "INTRADAY_MOM"]
P = dict(Tf=300, MaxSpreadOfRisk=0.15, AtrPeriod=14, TrendEmaPeriod=200,
         SweepLookback=20, SweepWindow=3, SweepBufAtr=0.25, SweepMaxStopAtr=2.0, SweepRR=2.0, SweepCooldown=3,
         OrbRangeBars=1, OrbRR=10.0, OrbHoldHours=6,
         RsiPeriod=2, RsiLow=5.0, RsiHigh=95.0, ExitSma=5, Rsi2StopAtr=1.5, Rsi2MaxBars=24,
         PbFast=20, PbMid=50, PbRR=2.0, PbSwingBars=5, PbMaxStopAtr=2.5,
         AsiaStartUtc=0, AsiaEndUtc=7, ManipEndUtc=10, DistEndUtc=20, AmdSweepAtr=0.10, AmdBufAtr=0.10, AmdRR=2.0,
         ImStopAtr=2.0, ImMinMovePct=0.0)


def ema(x, n):
    a = 2.0 / (n + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def sma(x, n):
    out = np.full_like(x, np.nan)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def atr(h, l, c, n):
    tr = np.zeros_like(c)
    tr[1:] = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    out = np.zeros_like(c)
    for i in range(n, len(c)):
        out[i] = tr[i - n + 1:i + 1].mean() if i == n else out[i - 1] + (tr[i] - tr[i - n]) / n
    return out


def rsi(c, n):
    out = np.full_like(c, np.nan)
    d = np.diff(c, prepend=c[0])
    pos = neg = 0.0
    for i in range(1, len(c)):
        if i < n:
            continue
        if i == n:
            pos = np.clip(d[1:n + 1], 0, None).mean()
            neg = np.clip(-d[1:n + 1], 0, None).mean()
        else:
            pos = (pos * (n - 1) + max(d[i], 0.0)) / n
            neg = (neg * (n - 1) + max(-d[i], 0.0)) / n
        out[i] = 100.0 - 100.0 / (1.0 + pos / neg) if neg != 0 else (100.0 if pos != 0 else 50.0)
    return out


def nth_sunday_utc(year, month, nth):
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    add = (6 - first.weekday()) % 7  # python: Monday=0 .. Sunday=6
    return int((first + timedelta(days=add + 7 * (nth - 1), hours=7)).timestamp())


_dst = {}


def us_dst(ts):
    y = datetime.fromtimestamp(ts, tz=timezone.utc).year
    if y not in _dst:
        _dst[y] = (nth_sunday_utc(y, 3, 2), nth_sunday_utc(y, 11, 1))
    a, b = _dst[y]
    return a <= ts < b


def ny_to_utc_min(ts, h, m):
    return (h + (4 if us_dst(ts) else 5)) * 60 + m


@dataclass
class Trade:
    method: int
    dir: int
    entry: float
    stop: float
    target: float
    spread: float
    opened: int
    maxBars: int
    flatAt: int
    bars: int = 0


@dataclass
class Stats:
    trades: list = field(default_factory=list)  # (opened, closed, dir, R, why)
    skipped: int = 0


def run(t, o, h, l, c, sp):
    n = len(t)
    A = atr(h, l, c, P["AtrPeriod"])
    TR = ema(c, P["TrendEmaPeriod"])
    RS = rsi(c, P["RsiPeriod"])
    SM = sma(c, P["ExitSma"])
    FA = ema(c, P["PbFast"])
    MI = ema(c, P["PbMid"])
    Tf = P["Tf"]
    trade = [None] * 7
    stats = [Stats() for _ in range(7)]
    st = dict(sw_upBar=-1, sw_dnBar=-1, sw_lastSig=-10 ** 9, sw_upLvl=0, sw_upExt=0, sw_dnLvl=0, sw_dnExt=0,
              orb_day=-1, orb_count=0, orb_done=False, orb_hi=0, orb_lo=0, orb_open=0, orb_time=0,
              amd_day=-1, amd_ready=False, amd_hi=0, amd_lo=0, amd_sH=False, amd_sL=False, amd_mH=0, amd_mL=0,
              amd_done=False, amd_start=0,
              im_day=-1, im_prev=0.0, im_r1=0.0, im_have=False, im_done=False)

    def open_virtual(i, mid, d, stop, rr, maxBars, flatAt):
        if trade[mid] is not None:
            return False
        bid = o[i]
        ask = o[i] + sp[i]
        entry = ask if d > 0 else bid
        spr = ask - bid
        risk = entry - stop if d > 0 else stop - entry
        if risk <= 0:
            return False
        if spr / risk > P["MaxSpreadOfRisk"]:
            stats[mid].skipped += 1
            return False
        target = entry + d * rr * risk if rr > 0 else 0.0
        trade[mid] = Trade(mid, d, entry, stop, target, spr, int(t[i]), maxBars, flatAt)
        return True

    def manage(mid, j, sma1):
        tr = trade[mid]
        if tr is None:
            return
        tr.bars += 1
        d, spr = tr.dir, tr.spread
        risk = abs(tr.entry - tr.stop)
        hi = h[j] if d > 0 else h[j] + spr
        lo = l[j] if d > 0 else l[j] + spr
        cl = c[j] if d > 0 else c[j] + spr
        op = o[j] if d > 0 else o[j] + spr
        hitStop = lo <= tr.stop if d > 0 else hi >= tr.stop
        hitTgt = tr.target > 0 and (hi >= tr.target if d > 0 else lo <= tr.target)
        gapStop = op < tr.stop if d > 0 else op > tr.stop
        gapTgt = tr.target > 0 and (op > tr.target if d > 0 else op < tr.target)
        px, why = None, ""
        if gapStop:
            px, why = op, "stop (gap)"
        elif gapTgt:
            px, why = op, "target (gap)"
        elif hitStop:
            px, why = tr.stop, "stop"
        elif hitTgt:
            px, why = tr.target, "target"
        elif mid == 3 and ((d > 0 and c[j] > sma1) or (d < 0 and c[j] < sma1)):
            px, why = cl, "back to SMA"
        elif tr.maxBars > 0 and tr.bars >= tr.maxBars:
            px, why = cl, "time stop"
        elif tr.flatAt > 0 and t[j] + Tf >= tr.flatAt:
            px, why = cl, "session end"
        if px is None:
            return
        R = d * (px - tr.entry) / risk
        stats[mid].trades.append((tr.opened, int(t[j] + Tf), d, R, why))
        trade[mid] = None

    barNo = 0
    for i in range(n):  # i = forming bar r[0]; j = i-1 = closed bar r[1]
        barNo += 1
        if i + 1 < P["TrendEmaPeriod"] + 50 or i < 25:
            continue
        j = i - 1
        a1, tr1, rs1, sm1, f1, f2, m1 = A[j], TR[j], RS[j], SM[j], FA[j], FA[j - 1], MI[j]
        if not (a1 > 0) or np.isnan(rs1) or np.isnan(sm1):
            continue
        for mid in range(1, 7):
            manage(mid, j, sm1)

        # 1) Trex sweep
        L = P["SweepLookback"]
        hiRef = h[j - L:j].max()   # r[2..L+1]
        loRef = l[j - L:j].min()
        if h[j] > hiRef:
            if st["sw_upBar"] < 0 or barNo - st["sw_upBar"] > P["SweepWindow"]:
                st["sw_upLvl"], st["sw_upExt"] = hiRef, h[j]
            else:
                st["sw_upExt"] = max(st["sw_upExt"], h[j])
            st["sw_upBar"] = barNo
        if l[j] < loRef:
            if st["sw_dnBar"] < 0 or barNo - st["sw_dnBar"] > P["SweepWindow"]:
                st["sw_dnLvl"], st["sw_dnExt"] = loRef, l[j]
            else:
                st["sw_dnExt"] = min(st["sw_dnExt"], l[j])
            st["sw_dnBar"] = barNo
        if trade[1] is None and barNo - st["sw_lastSig"] > P["SweepCooldown"]:
            W = P["SweepWindow"]
            sell = st["sw_upBar"] >= 0 and barNo - st["sw_upBar"] <= W and c[j] < st["sw_upLvl"] and c[j] < o[j] and c[j] < tr1
            buy = st["sw_dnBar"] >= 0 and barNo - st["sw_dnBar"] <= W and c[j] > st["sw_dnLvl"] and c[j] > o[j] and c[j] > tr1
            if sell:
                stop = st["sw_upExt"] + P["SweepBufAtr"] * a1
                if 0 < stop - c[j] <= P["SweepMaxStopAtr"] * a1 and open_virtual(i, 1, -1, stop, P["SweepRR"], 0, 0):
                    st["sw_lastSig"], st["sw_upBar"] = barNo, -1
            elif buy:
                stop = st["sw_dnExt"] - P["SweepBufAtr"] * a1
                if 0 < c[j] - stop <= P["SweepMaxStopAtr"] * a1 and open_virtual(i, 1, 1, stop, P["SweepRR"], 0, 0):
                    st["sw_lastSig"], st["sw_dnBar"] = barNo, -1

        # 2) ORB (09:30 New York)
        u = int(t[j])
        day = u // 86400
        dtj = datetime.fromtimestamp(u, tz=timezone.utc)
        dow = (dtj.weekday() + 1) % 7  # MQL: Sunday=0
        if dow not in (0, 6):
            mins = dtj.hour * 60 + dtj.minute - ny_to_utc_min(u, 9, 30)
            if day != st["orb_day"]:
                st["orb_day"], st["orb_count"], st["orb_done"] = day, 0, False
            if not st["orb_done"] and mins >= 0:
                if st["orb_count"] == 0 and mins != 0:
                    st["orb_done"] = True
                elif st["orb_count"] < P["OrbRangeBars"]:
                    if st["orb_count"] == 0:
                        st["orb_hi"], st["orb_lo"], st["orb_open"], st["orb_time"] = h[j], l[j], o[j], u
                    else:
                        st["orb_hi"], st["orb_lo"] = max(st["orb_hi"], h[j]), min(st["orb_lo"], l[j])
                    st["orb_count"] += 1
                    if st["orb_count"] >= P["OrbRangeBars"]:
                        st["orb_done"] = True
                        d = 1 if c[j] > st["orb_open"] else (-1 if c[j] < st["orb_open"] else 0)
                        if d != 0:
                            stop = st["orb_lo"] if d > 0 else st["orb_hi"]
                            open_virtual(i, 2, d, stop, P["OrbRR"], 0, st["orb_time"] + P["OrbHoldHours"] * 3600)

        # 3) RSI(2)
        if trade[3] is None:
            if c[j] > tr1 and rs1 < P["RsiLow"]:
                open_virtual(i, 3, 1, c[j] - P["Rsi2StopAtr"] * a1, 0.0, P["Rsi2MaxBars"], 0)
            elif c[j] < tr1 and rs1 > P["RsiHigh"]:
                open_virtual(i, 3, -1, c[j] + P["Rsi2StopAtr"] * a1, 0.0, P["Rsi2MaxBars"], 0)

        # 4) EMA pullback
        if trade[4] is None:
            up = m1 > tr1 and f1 > m1
            dn = m1 < tr1 and f1 < m1
            S = P["PbSwingBars"]
            if up and l[j - 1] <= f2 and c[j] > f1 and c[j] > o[j]:
                stop = l[j - S + 1:j + 1].min() - 0.1 * a1
                if 0 < c[j] - stop <= P["PbMaxStopAtr"] * a1:
                    open_virtual(i, 4, 1, stop, P["PbRR"], 0, 0)
            elif dn and h[j - 1] >= f2 and c[j] < f1 and c[j] < o[j]:
                stop = h[j - S + 1:j + 1].max() + 0.1 * a1
                if 0 < stop - c[j] <= P["PbMaxStopAtr"] * a1:
                    open_virtual(i, 4, -1, stop, P["PbRR"], 0, 0)

        # 5) AMD
        hr = dtj.hour
        if day != st["amd_day"]:
            st.update(amd_day=day, amd_ready=False, amd_sH=False, amd_sL=False, amd_done=False, amd_start=day * 86400)
        if P["AsiaStartUtc"] <= hr < P["AsiaEndUtc"]:
            if not st["amd_ready"]:
                st.update(amd_hi=h[j], amd_lo=l[j], amd_ready=True)
            else:
                st["amd_hi"], st["amd_lo"] = max(st["amd_hi"], h[j]), min(st["amd_lo"], l[j])
        elif st["amd_ready"] and not st["amd_done"] and hr < P["DistEndUtc"]:
            if hr < P["ManipEndUtc"]:
                if h[j] > st["amd_hi"] + P["AmdSweepAtr"] * a1:
                    st["amd_mH"] = max(st["amd_mH"], h[j]) if st["amd_sH"] else h[j]
                    st["amd_sH"] = True
                if l[j] < st["amd_lo"] - P["AmdSweepAtr"] * a1:
                    st["amd_mL"] = min(st["amd_mL"], l[j]) if st["amd_sL"] else l[j]
                    st["amd_sL"] = True
            if trade[5] is None:
                flat = st["amd_start"] + P["DistEndUtc"] * 3600
                if st["amd_sH"] and not st["amd_sL"] and c[j] < st["amd_hi"] and c[j] < o[j]:
                    if open_virtual(i, 5, -1, st["amd_mH"] + P["AmdBufAtr"] * a1, P["AmdRR"], 0, flat):
                        st["amd_done"] = True
                elif st["amd_sL"] and not st["amd_sH"] and c[j] > st["amd_lo"] and c[j] > o[j]:
                    if open_virtual(i, 5, 1, st["amd_mL"] - P["AmdBufAtr"] * a1, P["AmdRR"], 0, flat):
                        st["amd_done"] = True

        # 6) Intraday momentum
        ct = u + Tf
        dct = datetime.fromtimestamp(ct, tz=timezone.utc)
        cday = ct // 86400
        m = dct.hour * 60 + dct.minute
        t10, t1530, t16 = ny_to_utc_min(ct, 10, 0), ny_to_utc_min(ct, 15, 30), ny_to_utc_min(ct, 16, 0)
        if cday != st["im_day"]:
            st.update(im_day=cday, im_have=False, im_done=False)
        cdow = (dct.weekday() + 1) % 7
        if cdow not in (0, 6):
            if m == t10 and st["im_prev"] > 0:
                st["im_r1"], st["im_have"] = c[j] / st["im_prev"] - 1.0, True
            if m == t16:
                st["im_prev"] = c[j]
            if st["im_have"] and not st["im_done"] and m == t1530 and trade[6] is None:
                st["im_done"] = True
                r1 = st["im_r1"]
                if not (abs(r1) * 100 < P["ImMinMovePct"] or r1 == 0.0):
                    d = 1 if r1 > 0 else -1
                    stop = c[j] - P["ImStopAtr"] * a1 if d > 0 else c[j] + P["ImStopAtr"] * a1
                    flat = u + (t16 - t1530) * 60
                    open_virtual(i, 6, d, stop, 0.0, 0, flat + Tf)
    return stats


def load(path):
    rows = [r.split(",") for r in gzip.open(path, "rt").read().splitlines()[1:] if r]
    a = np.array([[float(x) for x in r[:6]] for r in rows])
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]


def summarize(tr, skipped):
    R = np.array([x[3] for x in tr]) if tr else np.array([])
    n = len(R)
    if n == 0:
        return dict(n=0, win=0, net=0, avg=0, pf=0, dd=0, skipped=skipped, h1=0, h2=0)
    eq = np.cumsum(R)
    dd = (np.maximum.accumulate(np.maximum(eq, 0)) - eq).max()
    w, ls = R[R > 0].sum(), -R[R <= 0].sum()
    mid = 1775001600  # 2026-04-01 UTC: first half Oct-Mar, second half Apr-Sep
    h1 = sum(x[3] for x in tr if x[0] < mid)
    h2 = sum(x[3] for x in tr if x[0] >= mid)
    return dict(n=n, win=100 * (R > 0).mean(), net=R.sum(), avg=R.mean(), pf=(w / ls if ls > 0 else float("inf")),
                dd=dd, skipped=skipped, h1=h1, h2=h2)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("epics", nargs="*", help="e.g. GOLD US100 (default: every *_M5.csv.gz in the cache)")
    ap.add_argument("--cache", default=str(ROOT / "data" / "cache" / "capital_m1"))
    ap.add_argument("--report", help="also write a markdown table to this file")
    a = ap.parse_args()
    files = sorted(Path(a.cache).glob("*_M5.csv.gz"))
    if a.epics:
        files = [f for f in files if f.name.split("_M5")[0] in a.epics]
    lines = ["| Market | Method | Trades | Win % | Net R | Avg R | PF | Max DD R | Oct-Mar R | Apr-Sep R |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for f in files:
        epic = f.name.split("_M5")[0]
        stats = run(*load(f))
        for k in range(1, 7):
            s = summarize(stats[k].trades, stats[k].skipped)
            print(f"{epic:10s} {NAMES[k]:13s} trades {s['n']:5d} | win {s['win']:5.1f}% | net {s['net']:+7.1f}R | "
                  f"avg {s['avg']:+.3f}R | PF {s['pf']:.2f} | maxDD {s['dd']:.1f}R | halves {s['h1']:+.1f}/{s['h2']:+.1f}", flush=True)
            lines.append(f"| {epic} | {NAMES[k]} | {s['n']} | {s['win']:.1f} | {s['net']:+.1f} | {s['avg']:+.3f} | "
                         f"{s['pf']:.2f} | {s['dd']:.1f} | {s['h1']:+.1f} | {s['h2']:+.1f} |")
    if a.report:
        Path(a.report).write_text("\n".join(lines) + "\n")
        print("report:", a.report)
