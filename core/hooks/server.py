"""Inbound webhooks. Revenue rows are insertable only here."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.config import load_settings
from core.drivers.loader import load_driver
from core.envfile import load_env
from core.errors import CapabilityDisabled
from core.hooks.ingest import ingest_payment
from core.paths import Paths, default_home


def serve() -> None:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    port = int((settings.raw.get("paths") or {}).get("hooks_port") or 8790)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path in {"/health", "/v1/health"}:
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            spec = settings.drivers.get("payments") or {}
            try:
                driver = load_driver("payments", spec.get("name") or "disabled")
                event = driver.verify_webhook(body, {k: v for k, v in self.headers.items()})
            except CapabilityDisabled:
                self.send_response(501)
                self.end_headers()
                self.wfile.write(b'{"error":"payments driver disabled"}')
                return
            result = "skipped"
            if event:
                result = ingest_payment(paths, driver, event)
            payload = json.dumps({"ok": True, "result": result}).encode()
            code = 202 if result == "ignored" else 200
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    print(f"sabre-hooks on 127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
