from __future__ import annotations

import sqlite3

from core.errors import BugError, EscalateError, RetryableError, classify
from core.gate.server import http_for


def test_timeout_is_retryable():
    err = classify(TimeoutError("timed out"))
    assert isinstance(err, RetryableError)
    assert err.kind == "retryable"


def test_auth_is_escalate():
    class Fake:
        status_code = 401

        def __str__(self):
            return "401"

    err = classify(Fake())
    assert isinstance(err, EscalateError)
    assert http_for(err)[0] == 422


def test_unknown_is_bug():
    err = classify(RuntimeError("boom"))
    assert isinstance(err, BugError)
    code, body = http_for(err)
    assert code == 500
    assert body["class"] == "bug"


def test_sqlite_locked_is_retryable():
    err = classify(sqlite3.OperationalError("database is locked"))
    assert err.kind == "retryable"
    assert http_for(err)[0] == 503


def test_gate_invalid_json_is_classified_bug(sabre_home):
    from http.server import ThreadingHTTPServer
    from threading import Thread

    import httpx

    from core.config import load_settings
    from core.gate.server import make_handler

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(load_settings(sabre_home)))
    Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{httpd.server_address[1]}/v1/intents",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        assert r.status_code == 500
        assert r.json()["class"] == "bug"
        assert r.json().get("error")
    finally:
        httpd.shutdown()
