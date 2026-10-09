#!/bin/bash
# Trex - (1) restart the price server so the forward-test journal is live, (2) give Hermes two routines:
#   - Weekday morning brief (09:35 Riyadh): calendar, overnight moves, Capital.com sentiment, big-player
#     positioning (CFTC), last 7 days of alert results -> your Telegram.
#   - Saturday weekly review (10:05): which markets/alerts actually made or lost R, what to change.
# Hermes uses only public sources and your local read-only price server. No trading. 2026-09-29
set -u
bash "$HOME/trex/scripts/restart_price_server.sh"
printf 'Forward-test journal: '; curl -s -m 60 "http://127.0.0.1:8787/alerts/review?days=7" | head -c 160; echo
cd "$HOME/.hermes/hermes-agent" || exit 1
./venv/bin/python - <<'PY'
from cron.jobs import create_job, list_jobs
Q = "curl -s 'http://127.0.0.1:8787/quote?symbol=%s'"
MKTS = "GC%3DF BTC-USD GBPUSD%3DX ETH-USD CAD%3DX %5EGDAXI CHF%3DX BZ%3DF CL%3DF HG%3DF"
brief = f"""Morning trading brief for Emad (he is in Riyadh, UTC+3). Load the trex-universal skill first.
Use web search on PUBLIC sources only (central banks, economic calendars, EIA, CFTC, reputable news) and the local
read-only price server. Analysis only - never place or suggest automatic orders.
1) Today's high-impact events (time in Riyadh) for: Gold, Crude, Brent, Copper, GBP/USD, USD/CAD, USD/CHF,
   Germany 40, Bitcoin, Ethereum.
2) Live Capital.com snapshot: for each of {MKTS} run {Q % '<symbol>'} - note day change, spread and client
   long/short %; flag crowded retail positioning (>75% one side).
3) If a new CFTC Commitments of Traders report came out, the managed-money change for crude, gold, GBP, CAD, CHF.
4) Forward test: curl -s 'http://127.0.0.1:8787/alerts/review?days=7' - wins/losses and total R.
5) Focus: the 2-3 cleanest markets today and any to avoid (news, wide spread).
Max 14 short lines, plain text, name sources briefly."""
review = """Weekly Trex review for Emad. Load the trex-universal skill.
1) curl -s 'http://127.0.0.1:8787/alerts/review?days=7' and summarise: alerts, closed, win rate, total R, per market.
2) Compare with the backtest expectations in references/backtest_2026-09-29_all_markets.md and day_trading_playbook.md.
3) Recommend concrete changes (drop a market after 20+ closed alerts with negative R, keep winners), and say how much
   evidence there is. Remind: forward test ~50 alerts per market before risking real money.
Max 12 short lines, plain text. Analysis only."""
have = {j.get("name") for j in list_jobs(include_disabled=True)}
for name, prompt, sched in [("Trex morning brief", brief, "35 9 * * 1-5"), ("Trex weekly review", review, "5 10 * * 6")]:
    if name in have:
        print("already exists:", name); continue
    j = create_job(prompt=prompt, schedule=sched, name=name, deliver="telegram", skill="trex-universal")
    print("created:", name, "| next run:", j.get("next_run_at"))
PY
echo "Done - tell Claude 'done'."
