"""Hosted mirror. Snapshots must verify against a gate-held public key. Kill is the only unsigned write."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core.push.sign import verify_envelope

STATE = {"snapshot": None, "verified": False, "kill": False}


def make_handler(token: str, pubkey: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _auth(self) -> bool:
            if not token:
                return False
            return self.headers.get("Authorization") == f"Bearer {token}"

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                self._json(200, {"ok": True, "configured": bool(token and pubkey)})
                return
            if not self._auth():
                self.send_response(401)
                self.end_headers()
                return
            if path == "/kill":
                self._json(200, {"kill": STATE["kill"]})
                return
            if path in {"/", "/snapshot"}:
                if not STATE["verified"] or STATE["snapshot"] is None:
                    self._json(200, {"verified": False, "snapshot": None})
                    return
                snap = dict(STATE["snapshot"])
                snap.pop("secrets", None)
                self._json(200, {"verified": True, "snapshot": snap})
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            if not self._auth():
                self.send_response(401)
                self.end_headers()
                return
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid json"})
                return
            path = urlparse(self.path).path
            if path == "/snapshot":
                if not pubkey:
                    self._json(503, {"error": "SABRE_MIRROR_PUBKEY is required; refusing unsigned state"})
                    return
                if not verify_envelope(pubkey, body):
                    self._json(403, {"error": "snapshot signature invalid; not stored"})
                    return
                STATE["snapshot"] = body.get("snapshot")
                STATE["verified"] = True
                self._json(200, {"ok": True, "verified": True})
                return
            if path == "/kill":
                STATE["kill"] = True
                self._json(200, {"ok": True})
                return
            self.send_response(404)
            self.end_headers()

        def _json(self, code, obj):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve() -> None:
    token = os.environ.get("SABRE_MIRROR_TOKEN") or ""
    pubkey = os.environ.get("SABRE_MIRROR_PUBKEY") or ""
    port = int(os.environ.get("PORT") or 8080)
    print(f"sabre-mirror on 0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(token, pubkey)).serve_forever()


if __name__ == "__main__":
    serve()
