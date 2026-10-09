# TRAX Architecture

TRAX is layered on top of the existing T-REX code base. Nothing in
`agents/`, `strategies/`, `risk/`, `backtest/`, `reports/`, or `service/`
was rewritten. The old pipeline (manual `python main.py`, the Phase 9
supervisor, the `trigger_server.py` HTTP bridge for n8n) still runs
unchanged.

What was added is a dashboard-facing API, a persistent memory layer, a
0DTE-aware opportunity scanner, and a React dashboard.

## Layers

```
┌────────────────────────────────────────────────────────────────────┐
│  dashboard/        React + Vite + TypeScript dashboard (10 screens) │
│                     reads /api/v1/* from the FastAPI backend         │
└────────────────────────────────────────────────────────────────────┘
                               │
┌────────────────────────────────────────────────────────────────────┐
│  api/              FastAPI backend, mounted at /api/v1               │
│     routes/        one router per dashboard screen                   │
│     static files   serves dashboard/dist in production               │
└────────────────────────────────────────────────────────────────────┘
                               │
┌───────────────────────┐  ┌─────────────────────┐  ┌───────────────┐
│ scanner/              │  │ existing T-REX       │  │ memory/        │
│    0DTE engine        │  │   agents/            │  │   db.py        │
│    confidence score   │  │   strategies/        │  │   repository.py│
│    data quality       │  │   risk/              │  │   SQLite       │
│                       │  │   backtest/          │  │                │
│                       │  │   reports/           │  │                │
│                       │  │   service/           │  │                │
└───────────────────────┘  └─────────────────────┘  └───────────────┘
                               │
┌────────────────────────────────────────────────────────────────────┐
│  data/              yfinance primary · Tradier fallback · Polygon    │
│                      (Polygon price feed is NOT_AUTHORIZED on the    │
│                      current key — documented in PHASES.md)          │
└────────────────────────────────────────────────────────────────────┘
```

## Operating modes

`TRAX_MODE` is a single environment variable with three values:

| mode              | describe                                                                                      |
|-------------------|------------------------------------------------------------------------------------------------|
| `research`        | default. Scanner and backtest only. Nothing even simulates an order.                           |
| `paper`           | adds the Alpaca paper execution agent. The agent itself refuses non-paper hosts outright.      |
| `live-disabled`   | emergency stop. The dashboard surfaces this; the risk engine returns `emergency_stop.active`.  |

There is no `live` mode. `/api/v1/settings/mode` returns HTTP 403 for
any string resembling live execution, and the execution agent itself
hard-refuses any non-paper Alpaca endpoint (see
`agents/execution_agent.py:ALLOWED_HOST_FRAGMENT`).

## Data flow for a single scan

```
1. UI calls GET /api/v1/scanner/?only_0dte=true
2. api/routes/scanner.py → scanner.scan_universe
3. scan_universe iterates TRAX_UNIVERSE (SPX, SPY, QQQ, NVDA by default)
4. For each ticker: scan_ticker →
       data/quotes.get_quote    (yfinance intraday)
       data/options_client.get_options_chain  (yfinance → Tradier fallback)
       scanner.engine._assess_data_quality
       scanner.engine._confidence_score
5. Result is a list of OpportunityCandidate dicts, scored.
6. If persist=true, each is written to the scanner_candidates table.
```

## Memory

SQLite file at `data/trax.sqlite3`. Six tables, all with timestamps:

- `scanner_candidates` — every scan the user chose to persist
- `agent_runs` — one row per instrumented agent invocation
- `risk_events` — rejections, breaches, emergency-stop toggles
- `telegram_history` — delivery outcomes
- `research_notes` — free-form research memory the agents or the user adds
- `system_state` — small kv store (last mode, last universe, etc.)

The pre-existing JSON caches in `data/cache/` and the pre-existing
`logs/orders.jsonl` and `logs/signals.jsonl` are *not* replaced. They
remain the source of truth for ingest snapshots, filled orders, and
published signals. SQLite is for the newer dashboard-facing concerns.

## What's NOT yet connected

These are explicit adapter stubs. The Intelligence screen names each
one with "adapter required" and does not fabricate data.

- News / economic calendar feed
- Public-trader / public-AI prediction scraper
- Live quote push (dashboard polls every 15-20s instead of streaming)
- LLM-driven agent runs (the `agent_runs` table has the schema; the Phase 9
  supervisor and signal engine still need `start_agent_run` / `finish_agent_run`
  wrappers around their nodes before entries appear)

## Where to run the system

```
# Backend (FastAPI, port 8788)
python3 -m uvicorn api.main:app --port 8788

# Frontend dev server (port 5173, proxies /api/* to 8788)
cd dashboard && npm run dev

# Frontend production build (served by backend if present)
cd dashboard && npm run build
```

The existing n8n `trigger_server.py` on port 8787 keeps its daily cycle,
independent of this.
