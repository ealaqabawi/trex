#!/bin/bash
# Trex - connect Capital.com as the (read-only) price feed for the scanner and Hermes. 2026-09-29
# Asks for your Capital.com API key details (hidden), saves them only in ~/trex/.env,
# checks the login, restarts the local price server and tests it. Nothing secret is printed.
set -u
say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
TREX="$HOME/trex"; ENV="$TREX/.env"
cd "$TREX" || exit 1
touch "$ENV"; chmod 600 "$ENV"; cp -p "$ENV" "$ENV.bak-$(date +%Y%m%d-%H%M%S)"
setkey() {  # value comes from VAL so it never shows in the process list
  KEY="$1" python3 - "$ENV" <<'PY'
import os, re, sys
p = sys.argv[1]; k = os.environ["KEY"]; v = os.environ["VAL"]
s = open(p).read(); line = f"{k}={v}"
pat = re.compile(rf"^{re.escape(k)}=.*$", re.M)
s = pat.sub(lambda m: line, s) if pat.search(s) else s.rstrip("\n") + "\n" + line + "\n"
open(p, "w").write(s)
PY
}

say "1/3 Capital.com API key"
echo "   Where to get it: capital.com (web) > Settings > API integrations > Generate new key."
echo "   (Capital.com needs 2-step verification switched on first.) Name it e.g. 'Trex' and set its own password."
echo "   Tip: use a NEW key just for Trex, separate from the one Claude's connector uses."
read -r -s -p "   Paste the API key (hidden): " K; echo
read -r -p "   Capital.com login e-mail: " ID
read -r -s -p "   The API key's custom password (hidden): " PW; echo
[ -z "$K" ] || [ -z "$ID" ] || [ -z "$PW" ] && { echo "   Missing value - nothing changed."; exit 1; }
VAL="$K" setkey CAPITAL_API_KEY; VAL="$ID" setkey CAPITAL_IDENTIFIER; VAL="$PW" setkey CAPITAL_PASSWORD
grep -q '^CAPITAL_ENV=' "$ENV" || VAL=live setkey CAPITAL_ENV
unset K PW
printf '   Checking the login... '
.venv/bin/python3 - <<'PY'
from service import capital_feed as c
try:
    i = c.CLIENT.login_check()
    print("OK - %s %s account (%s)" % (i["env"], i["accountType"], i["currency"]))
except Exception as e:
    print("FAILED:", e); raise SystemExit(1)
PY
[ $? -ne 0 ] && { echo "   Fix the key/e-mail/password and run this script again."; exit 1; }

say "2/3 Restart the local price server"
pkill -f service.trigger_server 2>/dev/null; sleep 5
curl -s -m 5 http://127.0.0.1:8787/health >/dev/null || (nohup ./scripts/run_trigger_server.sh >> logs/trigger_server.out.log 2>> logs/trigger_server.err.log &)
for i in $(seq 1 15); do curl -s -m 2 http://127.0.0.1:8787/health >/dev/null && break; sleep 1; done

say "3/3 Test"
printf '   Status: '; curl -s -m 30 "http://127.0.0.1:8787/capital/status?check=1"; echo
printf '   Crude oil candles: '
curl -s -m 60 "http://127.0.0.1:8787/candles?symbol=CL%3DF&interval=5m" | python3 -c 'import json,sys
j=json.load(sys.stdin); r=j["chart"]["result"][0]; q=r["indicators"]["quote"][0]
print(len(r["timestamp"]), "candles from", r["meta"].get("source"), "- last close", q["close"][-1])'
printf '   Crude oil live quote: '
curl -s -m 30 "http://127.0.0.1:8787/quote?symbol=CL%3DF" | python3 -c 'import json,sys
q=json.load(sys.stdin); print(q.get("status"), "bid", q.get("bid"), "offer", q.get("offer"), "spread", q.get("spread"), "| clients long", q.get("clients_long_pct"), "%") if "bid" in q else print("FAILED", q)'
say "Done - tell Claude 'done'."
