# MT5 scalp signal monitor

`TrexScalpSignals.mq5` is a signal-only Expert Advisor for the existing failed-breakout rules. It reads the chart symbol's MT5 candles and reports a candidate signal after a closed bar. It contains no order-submission code and does not connect to Capital.com, n8n, or an external trading API.

The default candidate uses M1 candles, a 20-bar sweep range, 3-bar reclaim window, EMA(200) trend filter, ATR(14) stop buffer of 0.25 ATR, maximum stop of 2 ATR, and a 2R target. It suppresses overlapping virtual signals until the virtual stop or target is touched. If both are touched in one candle, the stop is counted first. The live spread must be no more than 10% of the stop distance.

These settings are research defaults, not a proven scalp strategy. The monitor's spread gate uses the current quote; it does not model historical spread, commission, slippage, latency, or financing. The virtual entry is the signal candle close and is not a broker fill. Do not infer profitability from its alerts.

## Install

1. In MT5, choose **File > Open Data Folder**.
2. Copy `TrexScalpSignals.mq5` into `MQL5/Experts/`.
3. Open the file in MetaEditor and compile it (F7). Compiler-verified on 2026-10-01 with MetaEditor build 6231: 0 errors, 0 warnings.
4. In MT5, refresh **Navigator > Expert Advisors**, then attach the EA to a chart. It uses its `SignalTimeframe` input, which defaults to M1.
5. Optional phone alerts: in MT5 go to **Tools > Options > Notifications**, enable push notifications and enter the MetaQuotes ID shown in the MT5 mobile app. The `PushToPhone` input (on by default) then sends each signal to your phone.
6. Keep **AutoTrading disabled**. The EA only prints and displays alerts; it has no code to submit orders.

## Validate

Use Strategy Tester with the broker's actual symbol and high-quality tick history. Inspect the Experts/Journal output and independently record virtual trades, spread, commission, slippage, win/loss R, drawdown, and missed/late signals. Compare multiple non-overlapping periods before considering the strategy further. M1 signals are especially sensitive to costs and feed differences.

This EA is not a real-account order adapter and does not provide a profit guarantee.

# Trex Scalp Lab (`TrexScalpLab.mq5`, v1.10)

A research EA that runs six scalping / day-trading methods side by side, **signal-only** (no order code at all).
Compiler-verified 2026-10-01, MetaEditor build 6231: 0 errors, 0 warnings.

| # | Method | Rules (defaults) | Background |
|---|---|---|---|
| 1 | Trex sweep | failed breakout of the 20-bar range, reclaim within 3 bars, EMA200 filter, stop 0.25 ATR beyond the sweep, 2R | our own strategy |
| 2 | Opening-range breakout | direction of the first 5-min candle after 09:30 New York (US summer/winter time handled), stop at the other side, 10R or flat after 6 h | Zarattini & Aziz (SSRN 4416622 / 4729284) |
| 3 | RSI(2) mean reversion | RSI(2) < 5 above EMA200 (buy) / > 95 below (sell), exit on close back over SMA(5), stop 1.5 ATR, max 24 bars | Connors-style short-term reversion |
| 4 | EMA pullback | EMA50 above EMA200 and EMA20 above EMA50, dip to EMA20, green close back above, stop below 5-bar swing, 2R | classic trend pullback |
| 5 | AMD / Power of Three | Asian range 00-07 UTC, one-sided sweep 07-10 UTC, close back inside, stop beyond sweep, 2R, flat 20:00 UTC | ICT/smart-money concept |
| 6 | Intraday momentum (new) | return from yesterday's 16:00 NY close to 10:00 NY today; trade that direction 15:30-16:00 NY, 2 ATR stop | Gao, Han, Li & Zhou, *Market intraday momentum*, J. Financial Economics 2018 |

Every trade is **virtual**: entry at the ask (buy) / bid (sell) on the bar after the signal, exits on bid candles with
the spread added for sells, stop counted first when stop and target are in one candle, a candle that opens beyond the
stop is filled at its open (gap), and a signal is skipped when the spread is more than 15% of the stop. No commission
or swap is modelled.

## 1-year result on Capital.com prices (2025-10-01 to 2026-09-30)

Run with `scripts/scalp_lab_bt.py`, the Python twin of this EA (same rules bar for bar), on 5-minute Capital.com
bid candles with the real spread on every bar. 12 markets, 31,049 virtual trades. Full table:
`~/.hermes/skills/trading/trex-universal/references/backtest_2026-10-01_mt5_scalp_lab.md`.

| Method | Net R, all 12 markets | Markets positive |
|---|---:|---:|
| Intraday momentum | -38.6 | 4 / 12 |
| AMD | -172.8 | 1 / 12 |
| Opening-range breakout | -214.0 | 2 / 12 |
| Trex sweep | -340.7 | 2 / 12 |
| RSI(2) | -537.0 | 1 / 12 |
| EMA pullback | -891.8 | 2 / 12 |

Only three combinations were positive in both half-years with 100+ trades: **DE40 intraday momentum** (+28.8R, PF 1.43),
**US100 opening-range breakout** (+18.9R, PF 1.11) and **GOLD intraday momentum** (+11.8R, PF 1.18). With 72
combinations tested, none of these is proof of an edge - forward-test them on alerts before risking money.

## Run it in the MT5 Strategy Tester yourself

The tester will not start without a broker login (MT5 says "account is not specified"), so sign in to your
Capital.com MT5 login first (File > Login to Trade Account - type the password yourself).

1. Copy `TrexScalpLab.mq5` to `MQL5/Experts/Trex/` and `TrexImportCustom.mq5` to `MQL5/Scripts/Trex/`; compile both (F7).
2. Optional but recommended - test on the exact Capital.com prices used above:
   `python3 ~/trex/scripts/capital_to_mt5.py` writes `MQL5/Files/trex_import/*.bin` (default target is the Mac MT5
   app's data folder). Then drag **Scripts > Trex > TrexImportCustom** onto any chart. It creates custom symbols
   `GOLD.cap`, `US100.cap`, `DE40.cap` ... (market data only).
3. Strategy Tester (Ctrl+R): Expert `Trex\TrexScalpLab`, symbol `GOLD.cap` (or your broker symbol), period **M5**,
   dates 2025.10.01 - 2026.10.01, modelling **1 minute OHLC** for the `.cap` symbols ("Every tick based on real
   ticks" for broker symbols), inputs `ServerToUtcHours = 0` for `.cap` symbols (they are in UTC) or your broker's
   server offset for broker symbols, `Mode = All methods`.
4. Because no orders are sent, the Backtest tab shows 0 trades. The results are in the **Journal** tab (a table per
   method at the end), in `Common\Files\TrexScalpLab_<symbol>.csv` (one line per virtual trade) and as the
   optimisation criterion ("Custom max" = net R). They should match `scripts/scalp_lab_bt.py`.

Keep AutoTrading off. This EA cannot place orders, and live-account order automation is not part of this project.
