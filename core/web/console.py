"""Local console. 127.0.0.1 only. Full control. Never internet-exposed."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core.config import load_settings
from core.db import connect
from core.envfile import load_env
from core.paths import Paths, core_dir, default_home
from core.watch.client import request_kill, request_unkill
from core.watch.killswitch import is_killed


def _overview(settings) -> str:
    paths = settings.paths
    kill = "ENGAGED" if is_killed(paths) else "clear"
    ventures = 0
    spend = 0
    if paths.db.exists():
        conn = connect(paths.db)
        try:
            ventures = conn.execute(
                "SELECT COUNT(*) FROM ventures WHERE status NOT IN ('killed')"
            ).fetchone()[0]
            spend = conn.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit'"
            ).fetchone()[0]
        finally:
            conn.close()
    tmpl = (core_dir() / "web" / "templates" / "overview.html").read_text(encoding="utf-8")
    host, port = settings.console_bind
    return (
        tmpl.replace("{{kill}}", kill)
        .replace("{{ventures}}", str(ventures))
        .replace("{{spend}}", f"${spend/100:.2f}")
        .replace("{{no_spend}}", "yes" if settings.no_spend else "no")
        .replace("{{topology}}", settings.topology)
        .replace("{{host}}", host)
        .replace("{{port}}", str(port))
    )


def serve() -> None:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    host, port = settings.console_bind

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            path = urlparse(self.path).path
            if path in {"/", "/overview"}:
                body = _overview(settings).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/health":
                body = json.dumps({"ok": True, "kill": is_killed(paths)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/kill":
                request_kill(settings)
            elif path == "/unkill":
                request_unkill(settings)
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

    print(f"sabre-web http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
