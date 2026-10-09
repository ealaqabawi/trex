# Telegram integration

TRAX ships a direct Python Telegram sender in `utils/alerts.py`. The
n8n workflow at `n8n/daily_signal_cycle.json` is now optional / legacy.

## Setup (one command)

```bash
cd ~/trex
python3 scripts/setup_telegram.py --dry-run   # verify only; writes nothing
python3 scripts/setup_telegram.py             # write .env, send a test message
```

The script:

1. Takes the bot token from `~/trex/.env`, else from `~/.hermes/.env`
   (the Hermes agent already holds the working `@MyETRex_bot` token),
   else asks for it with hidden input. It never prints the token.
2. Checks the token with `getMe`. If Telegram can't be reached (for
   example, the python.org macOS build is missing its certificates), it
   says so instead of blaming the token.
3. Reads the chat id from config (`TELEGRAM_CHAT_ID`, or Hermes's
   `TELEGRAM_HOME_CHANNEL` / `TELEGRAM_ALLOWED_USERS`), else asks. To find
   your id, message `@userinfobot` in Telegram.
4. Backs up `.env` (mode 600), then sets `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, `TRAX_ALLOW_SETTINGS_WRITE=true` and
   `TELEGRAM_AUTOSEND=true` (pass `--no-autosend` to leave it off). Every
   other line is kept exactly as it was. A symlinked `.env` is followed.
5. Sends a test message, then offers to restart the
   `com.trex.trigger-server` LaunchAgent, the process that auto-sends
   signals and reads `.env` only at startup.

Then restart the dashboard backend yourself: Ctrl-C in its terminal, and
run `python3 -m uvicorn api.main:app --port 8788 --reload`. `--reload`
only watches `.py` files, so it does not notice `.env` changes.

**Why not `getUpdates`?** Hermes long-polls the same bot. A second
`getUpdates` caller gets `409 Conflict` and can take messages meant for
Hermes. `sendMessage` doesn't interfere, so TRAX only ever sends.

## Verifying it works

- Open the dashboard **Telegram** screen.
- Top status bar should flip `telegram` to `ok` with your `@botname`.
- Click **Verify bot** → green pill with `@yourbot`.
- Click **Send test** → "TRAX test message" appears in your Telegram chat.
- The Delivery History table shows the new row with `delivered` status.

From the terminal:
```bash
# Confirm the token works
curl http://127.0.0.1:8788/api/v1/telegram/verify

# Send a test message
curl -X POST http://127.0.0.1:8788/api/v1/telegram/test \
     -H 'Content-Type: application/json' -d '{}'
```

## How a signal reaches Telegram

With `TELEGRAM_AUTOSEND=true`:

```
service/trigger_server.py  /signal?tickers=…&actionable=true
   → build_signal()                        [service/signal_engine.py]
   → render_telegram(sig)                  [renders Markdown card]
   → publish_signal_to_telegram(sig)       [NEW — pushes to Bot API]
       → send_telegram_alert(body)         [utils/alerts.py]
           POST https://api.telegram.org/bot<token>/sendMessage
           → record_telegram(...)          [memory/repository.py]
   HTTP response includes telegram_delivery: {ok, error} per signal
```

Without `TELEGRAM_AUTOSEND`, nothing is pushed automatically — the
Telegram card is still rendered and returned in the HTTP response for
an external consumer (n8n or anything else) to post.

## Security notes

- The bot token is read from env on process start. It is never shipped
  to the browser. `/api/v1/telegram` returns only booleans and the bot
  username, never the token.
- Any error that includes the token in its text is passed through a
  redaction step before being returned to callers or logged.
- `POST /api/v1/telegram/test` and `/send` are gated behind
  `TRAX_ALLOW_SETTINGS_WRITE=true`. Without that flag they return 403
  so a compromised browser can't flood your chat.
- Both success and failure are logged to the `telegram_history` table
  (SQLite). You can audit every attempt on the dashboard.

## Troubleshooting

**`verify` returns `invalid_token`.** Your `TELEGRAM_BOT_TOKEN` is wrong.
Regenerate via BotFather's `/revoke` + `/newbot`.

**`verify` is `ok` but `test` returns `chat not found`.** Your
`TELEGRAM_CHAT_ID` doesn't match. Message the bot again and refetch
`/getUpdates`.

**Health probe still reads `unconfigured` after setting env.** Restart
the uvicorn process — env is read at startup. If you use `--reload`,
touching `.env` isn't enough; stop and start uvicorn.

**Dashboard test works but scheduled signals never arrive.** The
trigger server (`com.trex.trigger-server`, port 8787) is a separate
process that also read `.env` at startup. Restart it:
`launchctl kickstart -k gui/$(id -u)/com.trex.trigger-server`.

**`Could not reach api.telegram.org: … CERTIFICATE_VERIFY_FAILED`.** The
python.org macOS build has no CA store until you double-click
`/Applications/Python 3.13/Install Certificates.command`. Your token is
fine — don't rotate it.

**I want the old n8n flow.** Still shipped at
`n8n/daily_signal_cycle.json`. Import into n8n, replace all
`REPLACE_WITH_YOUR_CREDENTIAL_ID` placeholders with real credential ids,
export `TELEGRAM_CHAT_ID` in the n8n process env. The two paths can
coexist — the autosend path doesn't disable the HTTP response that n8n
reads.
