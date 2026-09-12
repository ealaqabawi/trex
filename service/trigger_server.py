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

        self._respond(404, {"status": "error", "detail": "unknown path"})

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
