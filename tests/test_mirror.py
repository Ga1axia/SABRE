from __future__ import annotations

from http.server import ThreadingHTTPServer
from threading import Thread

import httpx

from core.push.sign import ensure_keys, sign_snapshot
from core.web.mirror import STATE, make_handler


def test_mirror_rejects_unauthenticated_and_unsigned(sabre_home):
    STATE.update({"snapshot": None, "verified": False, "kill": False})
    ensure_keys(sabre_home)
    pubkey = sabre_home.mirror_verify_key.read_text(encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("secret-token", pubkey))
    Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        r = httpx.get(f"{base}/kill", timeout=5)
        assert r.status_code == 401
        r = httpx.get(f"{base}/snapshot", timeout=5)
        assert r.status_code == 401
        r = httpx.post(
            f"{base}/snapshot",
            json={"snapshot": {"ventures": [{"net": 999}]}, "signature": "forge"},
            headers={"Authorization": "Bearer secret-token"},
            timeout=5,
        )
        assert r.status_code == 403
        got = httpx.get(f"{base}/snapshot", headers={"Authorization": "Bearer secret-token"}, timeout=5)
        assert got.json()["verified"] is False
        assert got.json()["snapshot"] is None
        envelope = sign_snapshot(sabre_home, {"ventures": []})
        ok = httpx.post(
            f"{base}/snapshot",
            json=envelope,
            headers={"Authorization": "Bearer secret-token"},
            timeout=5,
        )
        assert ok.status_code == 200
        got = httpx.get(f"{base}/snapshot", headers={"Authorization": "Bearer secret-token"}, timeout=5)
        assert got.json()["verified"] is True
    finally:
        httpd.shutdown()


def test_empty_token_never_authorizes():
    STATE.update({"snapshot": None, "verified": False, "kill": False})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("", "not-a-key"))
    Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/kill", timeout=5)
        assert r.status_code == 401
        r = httpx.post(f"http://127.0.0.1:{port}/kill", json={}, timeout=5)
        assert r.status_code == 401
        health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5)
        assert health.status_code == 200
        assert health.json()["configured"] is False
    finally:
        httpd.shutdown()
