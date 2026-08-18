"""mTLS client for I1. The agent never opens the database."""

from __future__ import annotations

import json
import os
from typing import Any

from core.config import load_settings
from core.errors import EscalateError, RetryableError
from core.net import request as net_request
from core.paths import Paths, default_home


def _tls(paths: Paths) -> tuple[Any, Any]:
    if os.environ.get("SABRE_GATE_INSECURE") == "1":
        return False, None
    if not (paths.certs / "agent.crt").exists():
        return True, None
    return str(paths.certs / "ca.crt"), (str(paths.certs / "agent.crt"), str(paths.certs / "agent.key"))


def gate_url(paths: Paths | None = None) -> str:
    settings = load_settings(paths or Paths(default_home()))
    return os.environ.get("SABRE_GATE_URL") or settings.gate_url


def gate_request(paths: Paths, method: str, route: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = gate_url(paths).rstrip("/") + route
    verify, cert = _tls(paths)
    kwargs: dict[str, Any] = {"timeout": 30, "verify": verify, "cert": cert, "circuit": "gate"}
    if body is not None:
        kwargs["json"] = body
    try:
        r = net_request(method, url, **kwargs)
    except RetryableError as exc:
        return {"error": str(exc), "class": "retryable"}
    except EscalateError as exc:
        return {"error": str(exc), "class": "escalate"}
    raw = r.text
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"error": raw or f"HTTP {r.status_code}", "status": r.status_code}
    if r.status_code >= 400 and "error" not in parsed:
        parsed = {**parsed, "error": raw or f"HTTP {r.status_code}", "status": r.status_code}
    return parsed


def gate_post(paths: Paths, route: str, body: dict[str, Any]) -> dict[str, Any]:
    return gate_request(paths, "POST", route, body)


def gate_get(paths: Paths, route: str) -> dict[str, Any]:
    return gate_request(paths, "GET", route, None)
