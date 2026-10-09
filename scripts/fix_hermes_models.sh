#!/bin/bash
# Trex / Hermes - finish the model fix (2026-09-28)
# Claude already corrected ~/.hermes/.env, auth.json and config.yaml (backups: *.bak-before-keyfix-20260928).
# This script only does what has to run on the Mac itself:
#   1. un-blocks and runs "hermes update"   2. clears the old 401 cooldowns   3. restarts the Hermes gateway
#   4. tests the Hermes brain end-to-end and shows which model answered. No keys are printed.
set -u
say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
HERMES="$(command -v hermes || true)"
for c in "$HOME/.local/bin/hermes" "$HOME/.hermes/bin/hermes" "$HOME/.hermes/hermes-agent/venv/bin/hermes"; do
  [ -z "$HERMES" ] && [ -x "$c" ] && HERMES="$c"
done
[ -z "$HERMES" ] && { echo "Could not find the 'hermes' command."; exit 1; }
ENV="$HOME/.hermes/.env"; LOG="$HOME/.hermes/logs/agent.log"
getkey() { grep -E "^$1=" "$ENV" | tail -1 | cut -d= -f2-; }

say "1/4 Update Hermes"
cd "$HOME/.hermes/hermes-agent" || exit 1
rm -f .git/index.lock
git checkout -- package-lock.json 2>/dev/null && echo "   package-lock.json restored (it was blocking the update)."
echo "   Before: $("$HERMES" --version 2>/dev/null | head -1)"
"$HERMES" update || echo "   (update reported a problem - continuing with the current version)"
echo "   After:  $("$HERMES" --version 2>/dev/null | head -1)"
cd "$HOME"

say "2/4 Clear old Gemini cooldowns"
"$HERMES" auth reset gemini 2>/dev/null || echo "   (nothing to reset)"

say "3/4 Restart the Hermes gateway (Telegram + API for n8n)"
START_LINE=$(wc -l < "$LOG" 2>/dev/null || echo 0)
"$HERMES" gateway restart 2>/dev/null || { "$HERMES" gateway stop 2>/dev/null; "$HERMES" gateway start 2>/dev/null; } \
  || (nohup "$HERMES" gateway run --replace >/dev/null 2>&1 &)
printf '   Waiting for the API'
for i in $(seq 1 30); do curl -s -m 2 http://127.0.0.1:8642/health >/dev/null && break; printf '.'; sleep 2; done; echo
printf '   Health: '; curl -s -m 5 http://127.0.0.1:8642/health || echo "not up"; echo

say "4/4 Test the Hermes brain"
HKEY="$(getkey API_SERVER_KEY)" python3 - <<'PY'
import json, os, time, urllib.request
q = ("Trex test: a BUY signal fired on CL=F 5m at 93.25, stop 92.90, target 93.95. "
     "Using your trex-universal skill, reply in the exact n8n signal format (Verdict line + max 3 short lines).")
req = urllib.request.Request("http://127.0.0.1:8642/v1/chat/completions", method="POST",
      data=json.dumps({"model": "hermes-agent", "messages": [{"role": "user", "content": q}]}).encode(),
      headers={"Authorization": "Bearer " + os.environ["HKEY"], "Content-Type": "application/json"})
t = time.time()
try:
    with urllib.request.urlopen(req, timeout=240) as r:
        print("   Answer in %.0fs:\n" % (time.time() - t))
        print("   " + json.load(r)["choices"][0]["message"]["content"][:600].replace("\n", "\n   "))
except Exception as e:
    print("   No answer after %.0fs: %s" % (time.time() - t, e))
PY
echo; echo "   Model switches during the test (empty = the primary Gemini model answered):"
tail -n +"$((START_LINE+1))" "$LOG" 2>/dev/null | grep -E "Fallback activated|Fallback to .* failed|401|403" | tail -8 | cut -c1-200 | sed 's/^/   /'
"$HERMES" gateway status 2>/dev/null | tail -4
say "Done - tell Claude 'done'."
