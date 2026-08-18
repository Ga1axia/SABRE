from __future__ import annotations

from threading import Thread

import httpx

from core.config import load_settings
from core.watch.control import bind
from core.watch.killswitch import is_killed


def test_unkill_requires_operator_role(sabre_home):
    settings = load_settings(sabre_home)
    httpd = bind(settings, port=0)
    Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        r = httpx.post(f"http://127.0.0.1:{port}/kill", timeout=5)
        assert r.status_code == 200
        assert is_killed(sabre_home)
        r = httpx.post(f"http://127.0.0.1:{port}/unkill", timeout=5)
        assert r.status_code == 403
        assert is_killed(sabre_home)
        r = httpx.post(
            f"http://127.0.0.1:{port}/unkill",
            headers={"X-Sabre-Role": "operator"},
            timeout=5,
        )
        assert r.status_code == 200
        assert not is_killed(sabre_home)
    finally:
        httpd.shutdown()
