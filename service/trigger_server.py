"""
Local trigger server for n8n scheduling.

This n8n instance has no Execute Command (or similar shell-access) node
registered — likely disabled for security — so n8n can't shell out to
`python3 -m reports.daily_summary` directly. This tiny HTTP server bridges
that gap: n8n's Schedule Trigger calls an HTTP Request node against
GET /run-cycle, which runs the same pipeline and returns the summary text.

Binds to 127.0.0.1 only — not reachable outside this machine.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from reports.daily_summary import build_summary
from utils.logger import get_logger

log = get_logger("trigger_server")

HOST = "127.0.0.1"
PORT = 8787
DEFAULT_WATCHLIST = ["AAPL", "NVDA", "SPY"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        log.info("%s - %s", self.client_address[0], format % args)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._respond(200, {"status": "ok"})
            return

        if parsed.path == "/run-cycle":
            query = parse_qs(parsed.query)
            tickers = query.get("tickers", [",".join(DEFAULT_WATCHLIST)])[0].split(",")
            try:
                summary = build_summary(tickers)
                self._respond(200, {"status": "ok", "summary": summary})
            except Exception as e:  # noqa: BLE001
                log.error("run-cycle failed: %s", e)
                self._respond(500, {"status": "error", "detail": str(e)})
            return

        if parsed.path == "/signal":
            query = parse_qs(parsed.query)
            tickers = query.get("tickers", [",".join(DEFAULT_WATCHLIST)])[0].split(",")
            only_actionable = query.get("actionable", ["false"])[0].lower() == "true"
            try:
                from dataclasses import asdict
                from service.signal_engine import build_signal, render_telegram, render_compact
                from reports.signal_log import log_signal

                signals = []
                for t in tickers:
                    sig = build_signal(t.strip())
                    if only_actionable and sig.direction == "NEUTRAL":
                        continue
                    log_signal(asdict(sig))  # feedback loop: only LONG/SHORT persist
                    signals.append({**asdict(sig), "telegram": render_telegram(sig),
                                     "compact": render_compact(sig)})

                signals.sort(key=lambda s: s["confidence"], reverse=True)
                self._respond(200, {
                    "status": "ok",
                    "count": len(signals),
                    "signals": signals,
                    # compact text for the LLM agents — see render_compact()
                    "prompt": "\n".join(s["compact"] for s in signals)
                               or "No actionable signals today.",
                    "telegram": "\n\n".join(s["telegram"] for s in signals)
                                 or "No actionable signals today.",
                })
            except Exception as e:  # noqa: BLE001
                log.error("signal failed: %s", e)
                self._respond(500, {"status": "error", "detail": str(e)})
            return

        if parsed.path == "/review":
            try:
                from reports.signal_log import review_pending, recent_hit_rate
                result = review_pending()
                self._respond(200, {"status": "ok", "reviewed": result,
                                     "hit_rate": recent_hit_rate()})
            except Exception as e:  # noqa: BLE001
                log.error("review failed: %s", e)
                self._respond(500, {"status": "error", "detail": str(e)})
            return

        self._respond(404, {"status": "error", "detail": "unknown path"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/vet":
            self._respond(404, {"status": "error", "detail": "unknown path"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            from utils.grounding import vet_commentary

            safe, rejected = vet_commentary(payload.get("commentary", ""),
                                             payload.get("source", ""))
            if rejected:
                log.warning("Commentary rejected — ungrounded numbers %s", rejected)
            self._respond(200, {"status": "ok", "commentary": safe,
                                 "rejected": rejected, "grounded": not rejected})
        except Exception as e:  # noqa: BLE001
            log.error("vet failed: %s", e)
            # Fail closed: on any error the commentary is dropped, never passed through.
            self._respond(200, {"status": "error", "commentary": "",
                                 "rejected": ["vet-error"], "detail": str(e)})

    def _respond(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log.info("Trigger server listening on http://%s:%d (run-cycle, health)", HOST, PORT)
    server.serve_forever()


if __name__ == "__main__":
    run()
