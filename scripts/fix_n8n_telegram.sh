#!/bin/bash
# Trex - give n8n the CURRENT @MyETRex_bot token (2026-09-28)
# n8n still had the old, revoked bot token, so "Send to Telegram" failed with "Authorization failed".
# This copies the working token Hermes already uses (~/.hermes/.env) into a NEW n8n credential
# named "Trex bot (current token)". Nothing is printed except the bot's name and the result.
set -u
TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$HOME/.hermes/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
N8N_KEY="$(grep -E '^N8N_API_KEY=' "$HOME/trex/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
[ -z "$TOKEN" ] && { echo "No TELEGRAM_BOT_TOKEN in ~/.hermes/.env"; exit 1; }
[ -z "$N8N_KEY" ] && { echo "No N8N_API_KEY in ~/trex/.env"; exit 1; }
TOKEN="$TOKEN" N8N_KEY="$N8N_KEY" python3 - <<'PY'
import json, os, urllib.request, urllib.error
tok, key = os.environ["TOKEN"], os.environ["N8N_KEY"]
def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
    except Exception as e: return "ERR", str(e)
c, b = call("https://api.telegram.org/bot%s/getMe" % tok)
if c != 200:
    print("Telegram rejected the token in ~/.hermes/.env (code %s). Stop here and tell Claude." % c); raise SystemExit(1)
print("1/2 Token OK for bot @%s" % json.loads(b)["result"]["username"])
H = {"X-N8N-API-KEY": key, "Content-Type": "application/json"}
data = {"accessToken": tok}
c, b = call("http://localhost:5678/api/v1/credentials/schema/telegramApi", headers=H)
if c == 200 and "baseUrl" in b: data["baseUrl"] = "https://api.telegram.org"
body = json.dumps({"name": "Trex bot (current token)", "type": "telegramApi", "data": data}).encode()
c, b = call("http://localhost:5678/api/v1/credentials", data=body, headers=H, method="POST")
if c == 200:
    print("2/2 Created n8n credential 'Trex bot (current token)'.")
else:
    print("2/2 n8n answered %s: %s" % (c, b.replace(tok, "***")[:200]))
PY
echo "Done - tell Claude 'done'."
