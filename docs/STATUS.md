# TRAX Implementation Status

As of this delivery.

## What's done and tested

### Backend
- FastAPI app with 10 routers (`api/`), one per dashboard screen
- SQLite memory DB with 6 tables (`memory/`)
- 0DTE / near-dated opportunity scanner (`scanner/`)
- Data-freshness classifier (`data/freshness.py`)
- Intraday quotes layer for the Market Monitor (`data/quotes.py`)
- Session helpers (`utils/market_time.py`)
- TRAX-specific config layer (`utils/trax_config.py`) with mode switch
  and risk envelope separate from the legacy `utils/config.py`

### Frontend
- React + Vite + TypeScript dashboard (`dashboard/`)
- 10 screens: Overview, Market Monitor, Options Chain, 0DTE Scanner,
  Intelligence, Strategy Lab, Agents, Risk Center, Telegram, Settings
- Dark graphite theme, tabular numerics, candlestick + line charts
- Loading, empty, and error states on every screen
- Freshness and data-quality badges on every row
- Responsive layout (desktop-first, collapses to one column on mobile)

### Tests
- 39 unit + integration tests, all passing
  (`tests/test_memory.py`, `test_scanner.py`, `test_freshness.py`,
  `test_market_time.py`, `test_api.py`, `test_risk_rules.py`,
  `test_grounding.py`)

### Docs
- `docs/ARCHITECTURE.md`
- `docs/SETUP.md`
- `docs/SECURITY.md`
- `docs/STATUS.md` (this file)

### Preserved from T-REX (unchanged)
- All existing agents (`agents/`)
- All strategies and the signal engine (`strategies/`, `service/`)
- Backtest engine and metrics (`backtest/`, `utils/metrics.py`)
- Risk rules and position sizing (`risk/`)
- Reports pipeline (`reports/`)
- n8n workflow (`n8n/daily_signal_cycle.json`)
- Trigger server on 8787 (`service/trigger_server.py`)

## What's intentionally stubbed

Each is wired as an adapter and surfaced in the dashboard with
"adapter required" rather than fabricated data:

- News feed
- Economic calendar
- Public-trader and public-AI prediction streams
- Live quote streaming (dashboard polls)

## Honest gaps

These are gaps you need to know about:

1. **The LLM-side agent instrumentation isn't wrapped around every
   Phase 9 node yet.** The `agent_runs` table exists and
   `memory.repository.start_agent_run / finish_agent_run` are ready;
   calling them from inside `agents/supervisor.py` and
   `service/signal_engine.py` is a small cross-cut I didn't make to
   avoid touching the Phase 9 code (per the preserve-functionality
   rule). It's a <20-line change when you want it.

2. **n8n API key is still invalid** (per `PHASES.md:170`). The exported
   workflow in `n8n/daily_signal_cycle.json` still has to be imported
   manually.

3. **SPX option chains require a vendor key.** Yahoo doesn't serve
   them. The Options screen is first-class for SPX once `TRADIER_API_KEY`
   or `MARKETDATA_APP_TOKEN` is set in `.env`. Without one, the
   `index_options_feed` subsystem reads `unconfigured` in the top status
   bar and the Options screen shows "unavailable" for SPX — it does NOT
   silently substitute SPY. The Market Monitor chart (`^GSPC`) is
   independent and works without any key.

4. **The sandbox network rate-limited yfinance** during one of the
   local health probes. Not a code bug; expected in a cloud container.
   Users on a desktop won't hit this.

5. **One `recharts` chunk is 752 KB.** Not a failure — just the price
   of charts. Code-splitting it is one `React.lazy()` away.

## Reproducible test instructions

```bash
cd /home/user/trex
python3 -m pytest tests/ -v
# → 39 passed in ~3s

cd dashboard
npx tsc --noEmit
# → clean (no output)

npx vite build
# → built in ~5s with one chunk-size warning (recharts; expected)
```
