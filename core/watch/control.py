"""Localhost kill-control HTTP. The only process that writes the kill file."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core.config import Settings
from core.watch.killswitch import engage, is_killed, release


def make_handler(settings: Settings):
    paths = settings.paths

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in {"/health", "/status"}:
                self._send(200, {"ok": True, "kill": is_killed(paths)})
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            path = urlparse(self.path).path
            if path == "/kill":
                engage(paths)
                self._send(200, {"ok": True, "kill": True})
                return
            if path == "/unkill":
                if self.headers.get("X-Sabre-Role") != "operator":
                    self._send(403, {"error": "unkill is operator-only"})
                    return
                release(paths)
                self._send(200, {"ok": True, "kill": False})
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def bind(settings: Settings, port: int | None = None) -> ThreadingHTTPServer:
    if port is None:
        port = int((settings.raw.get("paths") or {}).get("watch_port") or 8791)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(settings))
    return httpd
