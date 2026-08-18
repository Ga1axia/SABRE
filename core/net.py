"""Outbound I/O: exponential backoff with full jitter, and a durable circuit breaker."""

from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from core.errors import CircuitOpen, RetryableError, classify
from core.paths import Paths, default_home

T = TypeVar("T")

SLEEP = time.sleep
TIME = time.time
RANDOM = random.random

PROFILES = {
    "rpc": {"attempts": 5, "base": 0.5, "cap": 30.0},
    "alert": {"attempts": 2, "base": 0.25, "cap": 2.0},
    "probe": {"attempts": 2, "base": 0.2, "cap": 1.0},
}

THRESHOLD = 5
COOLDOWN = 60.0
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}

_lock = threading.Lock()
_breakers: dict[str, dict[str, Any]] = {}
_on_open: Callable[[str], None] | None = None
_on_close: Callable[[str], None] | None = None


def set_hooks(*, on_open: Callable[[str], None] | None = None, on_close: Callable[[str], None] | None = None) -> None:
    global _on_open, _on_close
    _on_open = on_open
    _on_close = on_close


def reset_for_tests() -> None:
    with _lock:
        _breakers.clear()
    try:
        path = _state_path()
        if path.exists():
            path.unlink()
    except Exception:
        pass


def backoff_seconds(attempt: int, base: float, cap: float) -> float:
    """Full jitter: uniform(0, min(cap, base * 2**attempt))."""
    upper = min(cap, base * (2**attempt))
    return RANDOM() * upper


def call(
    fn: Callable[[], T],
    *,
    circuit: str | None = None,
    profile: str = "rpc",
) -> T:
    cfg = PROFILES[profile]
    attempts = int(cfg["attempts"])
    base = float(cfg["base"])
    cap = float(cfg["cap"])
    last: BaseException | None = None
    for i in range(attempts):
        if circuit:
            _before(circuit)
        try:
            result = fn()
            if circuit:
                _success(circuit)
            return result
        except Exception as exc:  # noqa: BLE001
            classified = classify(exc)
            last = classified
            if classified.kind != "retryable":
                raise classified from exc
            opened = _failure(circuit) if circuit else False
            if opened or i == attempts - 1:
                raise classified from exc
            SLEEP(backoff_seconds(i, base, cap))
    assert last is not None
    raise last


def request(
    method: str,
    url: str,
    *,
    circuit: str | None = None,
    profile: str = "rpc",
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
    json: Any = None,
    content: Any = None,
    verify: Any = True,
    cert: Any = None,
) -> httpx.Response:
    def once() -> httpx.Response:
        with httpx.Client(timeout=timeout, verify=verify, cert=cert) as client:
            r = client.request(method, url, headers=headers, json=json, content=content)
        if r.status_code in RETRY_STATUSES:
            raise RetryableError(f"HTTP {r.status_code} {url}", remedy=f"HTTP {r.status_code}")
        if r.status_code in {401, 403}:
            from core.errors import EscalateError

            raise EscalateError(f"HTTP {r.status_code} {url}", remedy="check credentials")
        return r

    return call(once, circuit=circuit, profile=profile)


def breaker_state(name: str) -> dict[str, Any]:
    with _lock:
        _load()
        b = dict(_breakers.get(name) or {"failures": 0, "state": "closed", "opened_at": 0.0})
    _maybe_half_open(name, b)
    return b


def _state_path():
    try:
        paths = Paths(default_home())
        paths.runtime.mkdir(parents=True, exist_ok=True)
        return paths.runtime / "circuits.json"
    except Exception:
        from pathlib import Path as _Path

        return _Path.cwd() / ".sabre-circuits-test.json"


def _load() -> None:
    path = _state_path()
    if not path.exists() or _breakers:
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(data, dict):
        _breakers.update(data)


def _save() -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_breakers), encoding="utf-8")
    tmp.replace(path)


def _breaker(name: str) -> dict[str, Any]:
    _load()
    if name not in _breakers:
        _breakers[name] = {"failures": 0, "state": "closed", "opened_at": 0.0}
    return _breakers[name]


def _maybe_half_open(name: str, b: dict[str, Any]) -> None:
    if b.get("state") == "open" and TIME() - float(b.get("opened_at") or 0) >= COOLDOWN:
        b["state"] = "half_open"


def _before(name: str) -> None:
    with _lock:
        b = _breaker(name)
        _maybe_half_open(name, b)
        if b["state"] == "open":
            raise CircuitOpen(f"circuit {name} open", remedy="wait for cooldown")


def _success(name: str) -> None:
    hook = False
    with _lock:
        b = _breaker(name)
        was = b["state"]
        b["failures"] = 0
        b["state"] = "closed"
        b["opened_at"] = 0.0
        _save()
        hook = was in {"open", "half_open"}
    if hook and _on_close:
        _on_close(name)


def _failure(name: str) -> bool:
    opened = False
    with _lock:
        b = _breaker(name)
        b["failures"] = int(b.get("failures") or 0) + 1
        if b["failures"] >= THRESHOLD and b["state"] != "open":
            b["state"] = "open"
            b["opened_at"] = TIME()
            opened = True
        _save()
    if opened and _on_open:
        _on_open(name)
    return opened or breaker_state(name).get("state") == "open"
