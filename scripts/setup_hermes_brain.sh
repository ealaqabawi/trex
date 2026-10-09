#!/bin/bash
# Trex Universal x Hermes Agent - one-time setup (safe to re-run).
# Run in Terminal:   bash ~/trex/scripts/setup_hermes_brain.sh
#
# What it does (secrets are typed hidden and never printed):
#  1. Saves your CURRENT Telegram bot token (@MyETRex_bot) for Hermes and locks Hermes' Telegram to your chat id.
#  2. Optionally saves an NVIDIA NIM key (free at build.nvidia.com) for the NVIDIA fallback models.
#  3. Turns on the Hermes API server (127.0.0.1:8642, local only) with a new random key.
#  4. Creates the n8n credential "Hermes API (Trex brain)" with that key, through the n8n API.
#  5. Updates Hermes Agent, restarts the Hermes gateway and the T-REX trigger server.
#  6. Checks: candles endpoint, Hermes API health, and a one-line test answer from Hermes.
set -u
say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ENV="$HOME/.hermes/.env"
TREX="$HOME/trex"
CHAT_ID=1156952811
HERMES="$(command -v hermes || true)"
for c in "$HOME/.local/bin/hermes" "$HOME/.hermes/bin/hermes" "$HOME/.hermes/hermes-agent/venv/bin/hermes"; do
  [ -z "$HERMES" ] && [ -x "$c" ] && HERMES="$c"
done
[ -z "$HERMES" ] && { echo "Could not find the 'hermes' command."; exit 1; }

cp -p "$ENV" "$ENV.bak-$(date +%Y%m%d-%H%M%S)"
# setkey NAME  (value comes from env var VAL so it never appears in the process list)
setkey() {
  KEY="$1" python3 - "$ENV" <<'PY'
import os, re, sys
p = sys.argv[1]; k = os.environ["KEY"]; v = os.environ["VAL"]
s = open(p).read()
line = f"{k}={v}"
pat = re.compile(rf"^{re.escape(k)}=.*$", re.M)
s = pat.sub(lambda m: line, s) if pat.search(s) else s.rstrip("\n") + "\n" + line + "\n"
open(p, "w").write(s)
PY
}
getkey() { grep -E "^$1=" "$ENV" | tail -1 | cut -d= -f2-; }

say "1/6 Telegram bot for Hermes"
read -r -s -p "Paste your CURRENT @MyETRex_bot token (Enter = keep the saved one): " TG; echo
if [ -n "$TG" ]; then
  if curl -s "https://api.telegram.org/bot${TG}/getMe" | grep -q '"ok":true'; then
    VAL="$TG" setkey TELEGRAM_BOT_TOKEN; echo "   Token accepted by Telegram and saved."
  else
    echo "   Telegram rejected that token - not saved. Check it in @BotFather (/mybots) and re-run."
  fi
fi
VAL="$CHAT_ID" setkey TELEGRAM_ALLOWED_USERS
VAL="$CHAT_ID" setkey TELEGRAM_HOME_CHANNEL
echo "   Hermes on Telegram now only answers you (chat $CHAT_ID)."

say "2/6 NVIDIA NIM key (optional)"
read -r -s -p "Paste an NVIDIA API key from build.nvidia.com (Enter = skip): " NV; echo
[ -n "$NV" ] && { VAL="$NV" setkey NVIDIA_API_KEY; echo "   Saved."; } || echo "   Skipped - NVIDIA fallback stays inactive."

say "3/6 Hermes API server (the n8n 'AI brain' link)"
NEWKEY=0
if [ -z "$(getkey API_SERVER_KEY)" ]; then
  VAL="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" setkey API_SERVER_KEY; NEWKEY=1
fi
VAL=true setkey API_SERVER_ENABLED; VAL=127.0.0.1 setkey API_SERVER_HOST; VAL=8642 setkey API_SERVER_PORT
echo "   Enabled on 127.0.0.1:8642 (not reachable from the internet)."

say "4/6 n8n credential 'Hermes API (Trex brain)'"
N8N_KEY="$(grep -E '^N8N_API_KEY=' "$TREX/.env" | cut -d= -f2-)"
if [ "$NEWKEY" = 1 ] || [ "${FORCE_N8N_CRED:-0}" = 1 ]; then
  if [ -n "$N8N_KEY" ]; then
    CODE=$(N8N_KEY="$N8N_KEY" HKEY="$(getkey API_SERVER_KEY)" python3 - <<'PY'
import json, os, urllib.request
body = json.dumps({"name": "Hermes API (Trex brain)", "type": "httpHeaderAuth",
                   "data": {"name": "Authorization", "value": "Bearer " + os.environ["HKEY"]}}).encode()
req = urllib.request.Request("http://localhost:5678/api/v1/credentials", data=body, method="POST",
      headers={"X-N8N-API-KEY": os.environ["N8N_KEY"], "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=20) as r: print(r.status)
except urllib.error.HTTPError as e: print(e.code)
except Exception as e: print("ERR", e)
PY
)
    [ "$CODE" = 200 ] && echo "   Created in n8n." || echo "   n8n answered $CODE - create it by hand: n8n > Credentials > Header Auth, name 'Authorization', value 'Bearer <API_SERVER_KEY from ~/.hermes/.env>'."
  else
    echo "   No N8N_API_KEY in ~/trex/.env - skipped."
  fi
else
  echo "   API key already existed - credential not recreated (run with FORCE_N8N_CRED=1 to force)."
fi

say "5/6 Update Hermes + restart services"
"$HERMES" update || echo "   (update reported a problem - continuing with the current version)"
"$HERMES" gateway restart 2>/dev/null || { "$HERMES" gateway stop 2>/dev/null; "$HERMES" gateway start 2>/dev/null; } \
  || (nohup "$HERMES" gateway run --replace >/dev/null 2>&1 &)
pkill -f service.trigger_server 2>/dev/null; sleep 4
curl -s -m 5 http://127.0.0.1:8787/health >/dev/null || (cd "$TREX" && nohup ./scripts/run_trigger_server.sh >> logs/trigger_server.out.log 2>> logs/trigger_server.err.log &)
sleep 10

say "6/6 Checks"
printf '   Trigger server candles (CL=F): '
curl -s -m 90 "http://127.0.0.1:8787/candles?symbol=CL%3DF&interval=5m&range=1d" | python3 -c 'import json,sys
try:
  j=json.load(sys.stdin); print(len(j["chart"]["result"][0]["timestamp"]), "candles OK")
except Exception as e: print("FAILED", e)'
printf '   Hermes API health: '; curl -s -m 5 http://127.0.0.1:8642/health || echo "not up yet (wait 30s and run: curl http://127.0.0.1:8642/health)"; echo
printf '   Hermes test answer: '
HKEY="$(getkey API_SERVER_KEY)" python3 - <<'PY'
import json, os, urllib.request
req = urllib.request.Request("http://127.0.0.1:8642/v1/chat/completions", method="POST",
      data=json.dumps({"model": "hermes-agent", "messages": [{"role": "user", "content": "In one short line: say OK, name the model you are running on, and name the Trex Universal trend filter."}]}).encode(),
      headers={"Authorization": "Bearer " + os.environ["HKEY"], "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        print(json.load(r)["choices"][0]["message"]["content"][:300])
except Exception as e:
    print("no answer yet:", e)
PY
"$HERMES" gateway status 2>/dev/null | tail -5
say "Done. Tell Claude 'done' so it can finish wiring n8n."
