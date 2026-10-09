# TRAX setup and recovery

## Prerequisites

- Python 3.11+ (tested on 3.13)
- Node 20+ (for the dashboard)
- An existing clone of this repo

## First-time setup

```bash
# 1. Python deps
pip install -r requirements.txt
pip install fastapi 'uvicorn[standard]' pytest httpx

# 2. Environment
cp .env.example .env
# Edit .env — nothing is REQUIRED for research mode. See the TRAX_* block
# at the bottom for TRAX-specific knobs.

# 3. Dashboard deps
cd dashboard && npm install && cd ..

# 4. Initialize the memory DB (optional; the API does this on startup)
python3 -c "from memory.db import init_db; init_db()"
```

## Running

### Development (two terminals)

```bash
# Terminal 1 — API
python3 -m uvicorn api.main:app --port 8788 --reload

# Terminal 2 — dashboard dev server with hot reload
cd dashboard && npm run dev
# → http://localhost:5173
```

### Production (one process)

```bash
cd dashboard && npm run build && cd ..
python3 -m uvicorn api.main:app --port 8788 --host 0.0.0.0
# → http://localhost:8788
```

### Existing T-REX pipeline (still runs)

```bash
python3 main.py                           # one-off cycle
python3 service/trigger_server.py         # n8n bridge on :8787
python3 reports.daily_summary             # daily digest
```

## Tests

```bash
python3 -m pytest tests/ -v
# Expect 39 passing.
```

## Backup and recovery

Everything mutable is on disk:

| path                        | contents                                     |
|-----------------------------|----------------------------------------------|
| `data/trax.sqlite3`         | Memory DB (scanner history, agent runs, risk events) |
| `data/cache/*.json`         | Last ingest snapshot per ticker              |
| `logs/orders.jsonl`         | Every attempted order (dry-run + real)       |
| `logs/signals.jsonl`        | Published signals with resolved outcomes     |
| `logs/trex.log`             | Rolling log                                  |

Backup = tar the project. The SQLite file is append-only in practice;
`sqlite3 data/trax.sqlite3 ".backup data/trax-backup.sqlite3"` gives you
a consistent snapshot without stopping the API.

To reset the memory DB (keeps everything else):

```bash
rm data/trax.sqlite3
python3 -c "from memory.db import init_db; init_db()"
```

## Troubleshooting

**`options feed: degraded` in the top status bar.**
yfinance occasionally rate-limits or returns an empty result. The API
degrades gracefully; the Options screen will show "no chain" rather
than fabricating one. Retry in a minute.

**`price_feed` always reads `polygon price entitlement is NOT_AUTHORIZED`.**
Expected — the Polygon key provided in `.env.example` is a placeholder.
yfinance is the primary and the detail string says so.

**`SPX` has no options.**
Yahoo serves SPX as `^GSPC` and does NOT list its options. The
dashboard charts the index via `data/quotes.py:_INDEX_PROXIES`, but
the Options screen falls back to SPY (the tradeable proxy). This is
labelled in the UI.

**`npm run build` warns about chunk size.**
Expected; this is a dense data-heavy UI. Not a failure.
