#!/bin/bash
# Restart the local Trex price server (127.0.0.1:8787: Capital.com + Yahoo candles, quotes) and check it.
cd "$HOME/trex" || exit 1
pkill -f service.trigger_server 2>/dev/null; sleep 5
curl -s -m 5 http://127.0.0.1:8787/health >/dev/null || (nohup ./scripts/run_trigger_server.sh >> logs/trigger_server.out.log 2>> logs/trigger_server.err.log &)
for i in $(seq 1 15); do curl -s -m 2 http://127.0.0.1:8787/health >/dev/null && break; sleep 1; done
printf 'Price server: '; curl -s -m 5 http://127.0.0.1:8787/health; echo
printf 'Crude oil on Capital.com: '
curl -s -m 30 "http://127.0.0.1:8787/quote?symbol=CL%3DF" | python3 -c 'import json,sys
q=json.load(sys.stdin); print(q.get("status"), "| bid", q.get("bid"), "offer", q.get("offer"), "| clients long", q.get("clients_long_pct"), "% short", q.get("clients_short_pct"), "%")'
