# T-REX — full phase plan

Designed by Claude Code on 2026-09-12, based on what's actually been built in
this repo. No prior master plan was ever shared with Claude Code — phases 1-2
below reconstruct what was described as already done; phases 5-12 are new.

**Non-negotiable constraint carried through every phase below:** T-REX never
places a live trade or moves real money autonomously. Phase 8 (execution)
targets paper/sandbox brokerage APIs only. Turning any part of this into
real-money automation is a decision only you make, outside of what an AI
assistant will build or run unattended.

---

## Phase 1 — Vision, Scope & Requirements
**Goal:** Define what T-REX is for, its data universe (US equities + options),
its risk posture (paper-trading intelligence, not unattended live trading),
and its agent boundaries.
**Deliverables:** this document; the constraint above.
**Status:** done (implicit in this plan).

## Phase 2 — Environment & Credentials Audit
**Goal:** Inventory available API keys, local tooling (Ollama/Hermes, n8n,
Python), and OS-level constraints.
**Deliverables:** confirmed Polygon key is `NOT_AUTHORIZED` for both
aggregates and options; n8n installed at `/usr/local/bin/n8n`.
**Status:** done (per your Terminal session's Phase 0 audit + this session's
curl test).

## Phase 3 — Repo Scaffolding & Infra
**Deliverables:** `agents/`, `data/`, `strategies/`, `utils/`, `logs/`;
`.env.example`; `.gitignore`; git init; pre-commit secret-blocking hook;
n8n LaunchAgent (auto-starts on login, verified reachable at :5678).
**Status:** done.

## Phase 4 — Agent Scaffolding & Data Ingestion Pipeline
**Deliverables:** `DataIngestionAgent` (LangGraph Observe/Reflect/Learn),
`AnalystAgent` (ReAct, LLM-optional with rule-based fallback),
`PolygonClient` with graceful 401/403 degradation, `options_client.py`
(yfinance primary, Tradier fallback), JSON cache in `data/cache/`.
**Status:** done. Polygon price aggregates are unauthorized on this key —
resolved in Phase 9 via a yfinance fallback in `data_agent.py` rather than
waiting on a new Polygon key.

## Phase 5 — Historical Data & Backtesting Engine
**Goal:** Let any strategy be scored against history before it ever touches
paper or real capital.
**Deliverables:** `data/historical.py` (yfinance-sourced OHLCV, since Polygon
price data is unauthorized), `backtest/engine.py` (vectorized backtest:
equity curve, total return, win rate, max drawdown, Sharpe), `backtest/run.py`
CLI, wired to run the existing `momentum` strategy.
**Depends on:** Phase 4 (strategies module, data caching pattern).
**Status:** done. Verified live: AAPL 1y (+12.0% vs +35.8% buy-and-hold,
Sharpe 0.69) and SPY 6mo (+6.4% vs +18.8% buy-and-hold, Sharpe 1.46) — the
momentum strategy underperforms buy-and-hold on both, which is a real,
useful finding for Phase 6 to act on, not a bug.

## Phase 6 — Strategy Library Expansion
**Goal:** Move beyond one momentum heuristic to a small, comparable library.
**Deliverables:** `strategies/mean_reversion.py`, `strategies/breakout.py`,
a common `Strategy` protocol (`(bars) -> (signal, reason)`), a
`strategies/registry.py` so the backtester and AnalystAgent can select by name.
**Depends on:** Phase 5 (backtester needed to compare strategies meaningfully).
**Status:** done. `strategies/registry.py` added. Verified 1y AAPL comparison:
momentum +12.0% (Sharpe 0.69), mean_reversion +11.0% (Sharpe 0.84, 75% win
rate, lowest drawdown), breakout +5.4% (Sharpe 0.40) — all below buy-and-hold
(+36%) in this trending period, which is expected and exactly the kind of
result Phase 7's risk layer and Phase 11's live-vs-backtest tracking should
surface, not something to paper over.

## Phase 7 — Risk Management & Position Sizing
**Goal:** No signal reaches an execution agent without a position size and
a stop — a signal alone is not a trade plan.
**Deliverables:** `risk/position_sizing.py` (fixed-fractional sizing off
account equity), `risk/rules.py` (max position %, max daily loss, max
concurrent positions), a `RiskManagerAgent` that wraps AnalystAgent output
into a sized, risk-checked order proposal (never an executed order).
**Depends on:** Phase 6 (needs strategy signals to size).
**Status:** done. `risk/position_sizing.py` (fixed-fractional, stop-relative),
`risk/rules.py` (position/daily-loss/concurrency limits), `agents/risk_agent.py`.
Verified: normal BUY sizes correctly (8.7 shares, $2000, stop @ $218.50 off a
$230 entry); daily-loss-limit breach, max-concurrent-positions breach, and
HOLD passthrough all rejected/handled correctly.

## Phase 8 — Execution Agent (Paper Trading Only)
**Goal:** Let approved order proposals actually place paper trades, with a
human-in-the-loop switch for anything beyond paper.
**Deliverables:** `agents/execution_agent.py` using Alpaca's **paper**
endpoint (`ALPACA_BASE_URL=paper-api.alpaca.markets`, already the default in
`.env.example`), an explicit `DRY_RUN` default of `true`, and an order log.
**Hard boundary:** this phase, and this system, will not add a live-money
order path. That is a human decision made directly with a broker, not
something built into T-REX's autonomy loop.
**Depends on:** Phase 7 (sized, risk-checked proposals).
**Status:** done. `agents/execution_agent.py` built with two hard guardrails,
both verified live: (1) defaults to DRY_RUN — logs the order, submits
nothing, even with no env override; (2) refuses to submit to any endpoint
that isn't `paper-api.alpaca.markets`, even if `ALPACA_BASE_URL` is pointed
at the live host. No Alpaca credentials are configured, so nothing here can
place even a paper order yet — that's expected, not a gap to silently fix.

## Phase 9 — Multi-Agent Orchestration & Scheduling
**Goal:** Replace manual `python main.py` runs with a supervised, scheduled
pipeline (Ingest → Analyze → Risk-check → Paper-execute → Report).
**Deliverables:** `agents/supervisor.py` (LangGraph supervisor node routing
across the four agents), an n8n workflow that triggers a cycle on a market-
hours schedule via HTTP/CLI call into the supervisor.
**Depends on:** Phase 8 (needs a full agent chain to schedule).
**Status:** done (agent side). `agents/supervisor.py` chains
Ingest→Analyze→Price→Risk→Execute as one LangGraph pipeline. Also fixed a
Phase 4 gap along the way: `data_agent.py` now falls back to yfinance
historical bars when Polygon aggregates 401s, so signals are no longer
permanently stuck on HOLD. Verified live: AAPL HOLD (+1.24%), NVDA SELL
(-4.34%, correctly dry-run executed), SPY HOLD (-1.15%) — real signals from
real data, flowing end-to-end with no crashes. n8n scheduling (the workflow
side of this phase) is deferred to Phase 10 alongside monitoring, since both
touch the same "run this periodically and report" surface.

## Phase 10 — Monitoring, Logging & Alerting
**Goal:** Make failures and decisions visible without reading raw logs.
**Deliverables:** structured JSON logging for every agent decision (already
started via `utils/logger.py`), a `reports/daily_summary.py` that renders a
plain-text/HTML end-of-day digest, optional Slack/Discord webhook alert on
errors or risk-limit breaches (webhook URLs already stubbed in `.env.example`).
**Depends on:** Phase 9 (needs a running pipeline to monitor).
**Status:** mostly done. `utils/alerts.py` (Slack/Discord webhook, clean
no-op if unset — verified), `reports/daily_summary.py` (writes
`logs/daily_summary_YYYYMMDD.txt`, fires alerts on SELL signals or execution
errors — verified live, correctly flagged NVDA's SELL). n8n scheduling: the
`n8n-api` MCP server's API key is invalid/expired (401 on workflow creation)
so I could not create the schedule workflow programmatically — exported it
instead as `n8n/daily_signal_cycle.json` (cron `0 30 9-16 * * 1-5`, runs
`reports.daily_summary` via Execute Command) for manual import once you
issue a fresh n8n API key under Settings → n8n API.

## Phase 11 — Performance Reporting & Analytics
**Goal:** Track paper-trading performance over time the same way the
backtester tracks historical performance, so the two are comparable.
**Deliverables:** `reports/performance.py` — equity curve, win rate, Sharpe,
drawdown computed from the Phase 8 order log; a backtest-vs-live comparison
report to catch strategy decay.
**Depends on:** Phase 8 (order log) and Phase 5 (shared metrics code).
**Status:** done. `utils/metrics.py` extracted so `backtest/engine.py` and
`reports/performance.py` share the same drawdown/Sharpe/win-rate math.
`reports/performance.py` reads `logs/orders.jsonl` — verified it correctly
reports 1 dry-run SELL, 0 real fills, and says plainly that no real
paper-trading equity curve exists yet (no Alpaca credentials configured).

## Phase 12 — Options Data Integration & Options Strategies
**Goal:** Extend beyond equities into options-aware signals now that options
data is unblocked.
**Deliverables:** options chain analytics (IV, put/call ratio, unusual volume)
in `strategies/options_signals.py`, consuming `data/options_client.py`
(yfinance primary, Tradier fallback — already built in Phase 4).
**Status:** done. `strategies/options_signals.py` — put/call volume ratio,
average IV by side, unusual-volume detection, and `options_bias_signal()`.
Verified live: NVDA read call-heavy (PCR 0.46) → BUY bias; AAPL read neutral
(PCR 0.88) → HOLD. Not yet wired into the Phase 9 supervisor pipeline
alongside the price-based momentum signal — see Open Items.
**Depends on:** Phase 6 (strategy registry pattern) for consistency.

---

## All 12 phases: done, with two honest gaps

Every phase above has working, verified code — not stubs. Two things are
genuinely incomplete, both flagged in-line above and repeated here:

1. **n8n scheduling isn't live.** The `n8n-api` MCP server's key is
   invalid/expired, so the Phase 10 workflow exists only as
   `n8n/daily_signal_cycle.json`, waiting on a fresh key to import.
2. **Options signals aren't wired into the main pipeline yet.** Phase 12's
   `options_bias_signal()` works standalone but `agents/supervisor.py`
   still only acts on the price-based momentum signal. Combining the two
   (e.g. requiring price and options bias to agree before sizing a trade)
   is a real design decision, not a mechanical wiring step, so I left it
   for you to weigh in on rather than picking silently.

Also worth restating: **no real money has moved and none will move
autonomously.** `DRY_RUN=true` by default, no Alpaca credentials are
configured, and the execution agent refuses any non-paper endpoint outright.
Everything executed in this session against live data was read-only market
data pulls (yfinance, Polygon) plus simulated/dry-run order logging.
