# Telegram integration

TRAX ships a direct Python Telegram sender in `utils/alerts.py`. The
n8n workflow at `n8n/daily_signal_cycle.json` is now optional / legacy.

## Setup (two minutes)

1. In Telegram, message `@BotFather`, send `/newbot`, pick a name and
   a username ending in `bot`. BotFather returns a token that looks like
   `9999999999:AAE…`.
2. In Telegram, send any message to your new bot from your personal
   account.
3. Visit `https://api.telegram.org/bot<THE_TOKEN>/getUpdates` in a
   browser. Look for `"chat":{"id":<number>,…}` — that number is your
   `chat_id`.
4. In `~/trex/.env`:
   ```
   TELEGRAM_BOT_TOKEN=9999999999:AAE…
   TELEGRAM_CHAT_ID=<the-number-from-step-3>
   TRAX_ALLOW_SETTINGS_WRITE=true    # required to send from the dashboard
   TELEGRAM_AUTOSEND=true            # optional: push every actionable signal
   ```
5. Restart the uvicorn backend.

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

**I want the old n8n flow.** Still shipped at
`n8n/daily_signal_cycle.json`. Import into n8n, replace all
`REPLACE_WITH_YOUR_CREDENTIAL_ID` placeholders with real credential ids,
export `TELEGRAM_CHAT_ID` in the n8n process env. The two paths can
coexist — the autosend path doesn't disable the HTTP response that n8n
reads.
