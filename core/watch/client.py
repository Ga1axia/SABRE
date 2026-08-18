"""Localhost client for the watcher. The agent may request kill, never unkill."""

from __future__ import annotations

import json
import os

from core.config import Settings, load_settings
from core.errors import EscalateError, RetryableError
from core.net import request as net_request
from core.paths import Paths, default_home


def _url(settings: Settings | None = None) -> str:
    settings = settings or load_settings(Paths(default_home()))
    return os.environ.get("SABRE_WATCH_URL") or settings.watch_url


def _post(path: str, operator: bool = False, settings: Settings | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if operator:
        headers["X-Sabre-Role"] = "operator"
    try:
        r = net_request(
            "POST",
            _url(settings).rstrip("/") + path,
            circuit="watch",
            profile="probe",
            headers=headers,
            json={},
            timeout=5,
        )
    except RetryableError as exc:
        raise RuntimeError(f"watcher unreachable at {_url(settings)} ({exc}). Start sabre-watch.") from exc
    except EscalateError as exc:
        raise RuntimeError(f"watcher refused: {exc}") from exc
    raw = r.text
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"error": raw, "status": r.status_code}
    if r.status_code >= 400:
        raise RuntimeError(f"watcher {r.status_code}: {raw}")
    return parsed


def request_kill(settings: Settings | None = None) -> dict:
    return _post("/kill", operator=False, settings=settings)


def request_unkill(settings: Settings | None = None) -> dict:
    return _post("/unkill", operator=True, settings=settings)
