# Security & Limitations Report

## Threat model

TRAX is a local-first platform. The API binds to `127.0.0.1` by default
and should not be exposed on a public network without putting an
authenticated reverse proxy in front of it — none of its endpoints
authenticate the caller.

## What's protected

- **Secrets are never shipped to the browser.** `/api/v1/settings/` returns
  only booleans like `telegram_configured`, not the token itself.
- **Live execution is a hard disabled default.**
  - `/api/v1/settings/mode` returns HTTP 403 for any string resembling
    live execution.
  - The execution agent (`agents/execution_agent.py`) refuses to submit
    to any host whose URL doesn't contain `paper-api.alpaca.markets`.
  - `DRY_RUN=true` by default; if either Alpaca credential is missing,
    the agent falls back to dry-run even if `DRY_RUN=false`.
- **External content is treated as data.** The `utils/grounding.py`
  module strips LLM commentary that cites numbers absent from its
  source. External JSON (news, forums, scraped predictions when the
  adapter is wired) is passed to agents as data, never as instructions.
- **Prompt injection via chain content is contained.** The LLM-written
  commentary endpoint (`/vet` on the trigger server) fails closed:
  on any grounding failure the commentary is dropped entirely rather
  than passed through with a surgically removed figure.
- **No raw chain-of-thought is exposed.** The AI Agent Activity screen
  shows `agent / task / status / detail / tokens`, not the model's
  internal reasoning.
- **Settings writes are gated.** Even non-live mode changes require
  `TRAX_ALLOW_SETTINGS_WRITE=true`.
- **The risk engine is independent of the LLM.** It runs before any
  execution attempt, has its own tests, and has limits that are
  configurable but never hard-coded as personal assumptions.

## What's NOT protected (yet)

- **No authentication.** Anyone with network access to the API port can
  read every endpoint. Fine for localhost; not fine on a shared network.
- **No request rate limiting.** A naive loop can exhaust the yfinance
  cache. The API tolerates this but will serve stale data.
- **No CSRF on `POST /api/v1/settings/mode`.** It's a localhost-only
  surface; add a token header if the API is ever exposed.
- **No TLS.** Uvicorn's dev server is HTTP; put nginx in front for TLS.
- **The intelligence sources index is static.** News and public-agent
  adapters are stubs. See `docs/ARCHITECTURE.md`.
- **n8n webhooks are the responsibility of the existing deployment.**
  `trigger_server.py` binds to 127.0.0.1 and that stays.

## Explicit non-features

- **No live execution path.** This is not an oversight. Live money is a
  human-authorized action with a broker. There is no code path that
  turns on from inside TRAX.
- **No fabricated market data.** If a feed is unavailable the UI shows
  "unavailable" and the API returns `ok: false`.
- **No social-media as prediction.** Agreement between agents is not
  evidence of profitability; the dashboard's Intelligence screen says so.
- **No continuous fine-tuning for memory updates.** Memory is SQLite.

## Operating constraints to carry forward

1. If live execution ever becomes a real feature, it must go through
   a broker-side authorization step the user performs outside TRAX.
2. The grounding check is one-directional — it catches invented
   numbers, not invented reasoning. LLM commentary should still be
   reviewed by a human before publication.
3. Every chart in the dashboard shows a freshness badge. If that
   badge ever quietly disappears for a screen, treat that as a bug,
   not a cleanup.
