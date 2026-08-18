"""Credential injection. Values stay in the proxy; the agent holds opaque tokens only."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core.config import load_settings
from core.errors import RetryableError
from core.net import request as net_request
from core.paths import Paths, default_home
from core.proxy.store import get_value_by_token, names
from core.runtime.provenance import wrap_fetched


def decorate_fetch(url: str, status: int, text: str, injected: bool) -> dict:
    host = urlparse(url).hostname or ""
    wrapped = wrap_fetched(text, host)
    return {
        "status": status,
        "body": wrapped["text"],
        "provenance": wrapped["provenance"],
        "injected": injected,
    }


def serve() -> None:
    settings = load_settings(Paths(default_home()))
    paths = settings.paths
    port = int((settings.raw.get("paths") or {}).get("proxy_port") or 8789)

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
            if self.path in {"/health", "/v1/health"}:
                self._send(200, {"ok": True, "mode": "inject", "secrets": len(names(paths))})
                return
            # No endpoint returns credential values.
            self._send(404, {"error": "not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/v1/fetch":
                self._send(404, {"error": "not found"})
                return
            n = int(self.headers.get("Content-Length") or 0)
            try:
                req = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"})
                return
            target = str(req.get("url") or "")
            if not target.startswith("https://"):
                self._send(400, {"error": "only https targets"})
                return
            headers = dict(req.get("headers") or {})
            token = str(
                self.headers.get("X-Sabre-Proxy-Token")
                or req.get("proxy_token")
                or headers.pop("X-Sabre-Proxy-Token", "")
                or ""
            )
            injected = get_value_by_token(paths, token) if token else None
            if injected:
                headers["Authorization"] = f"Bearer {injected}"
            try:
                r = net_request(
                    str(req.get("method") or "GET"),
                    target,
                    circuit=None,
                    headers=headers,
                    content=req.get("body"),
                    timeout=30,
                )
            except RetryableError as exc:
                self._send(502, {"error": str(exc), "class": "retryable"})
                return
            self._send(200, decorate_fetch(target, r.status_code, r.text[:65536], bool(injected)))

        def do_CONNECT(self):
            self.send_response(501)
            self.end_headers()

    print(f"sabre-proxy inject on 127.0.0.1:{port} secrets={len(names(paths))}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
