"""Capability flags and the runtime error taxonomy."""

from __future__ import annotations

import sqlite3
from typing import Literal

Kind = Literal["retryable", "escalate", "bug"]


class CapabilityDisabled(Exception):
    def __init__(self, slot: str, message: str | None = None):
        self.slot = slot
        super().__init__(message or f"{slot} driver is disabled")


class SabreError(Exception):
    """Operator-facing error with a remediation hint."""

    kind: Kind = "bug"

    def __init__(self, message: str, remedy: str = ""):
        super().__init__(message)
        self.remedy = remedy


class RetryableError(SabreError):
    """Transient: retry with backoff, then trip the circuit."""

    kind: Kind = "retryable"


class EscalateError(SabreError):
    """Needs the operator. Do not retry. Alert #requests."""

    kind: Kind = "escalate"


class BugError(SabreError):
    """Our fault. Do not retry. Alert #status."""

    kind: Kind = "bug"


class CircuitOpen(RetryableError):
    """Circuit breaker is open; fail fast until cooldown."""


def classify(exc: BaseException) -> SabreError:
    """Map any exception onto the taxonomy. Unknown becomes a bug."""
    if isinstance(exc, SabreError):
        return exc
    if isinstance(exc, TimeoutError):
        return RetryableError(str(exc) or "timeout")
    if isinstance(exc, ConnectionError | OSError):
        name = type(exc).__name__
        if name in {"ConnectionError", "ConnectionRefusedError", "ConnectionResetError", "BrokenPipeError"}:
            return RetryableError(str(exc) or name)
        if isinstance(exc, OSError) and getattr(exc, "errno", None) in {111, 61, 10061, 10054, 110, 60}:
            return RetryableError(str(exc) or name)
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return RetryableError(str(exc))
        return BugError(str(exc))
    status = _status_code(exc)
    if status in {408, 409, 425, 429, 500, 502, 503, 504}:
        return RetryableError(str(exc), remedy=f"HTTP {status}")
    if status in {401, 403}:
        return EscalateError(str(exc), remedy="check credentials")
    if _is_httpx_transient(exc) or _is_urllib_transient(exc):
        return RetryableError(str(exc))
    return BugError(str(exc) or type(exc).__name__)


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        if hasattr(exc, attr):
            val = getattr(exc, attr)
            if callable(val):
                continue
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    code = getattr(resp, "status_code", None)
    if code is None:
        code = getattr(resp, "status", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def _is_httpx_transient(exc: BaseException) -> bool:
    name = type(exc).__name__
    mod = type(exc).__module__ or ""
    if "httpx" not in mod and "httpcore" not in mod:
        return False
    return name in {
        "TimeoutException",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "NetworkError",
        "RemoteProtocolError",
        "ProxyError",
        "TransportError",
    }


def _is_urllib_transient(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in {"URLError", "TimeoutError"} and "error" in (type(exc).__module__ or "")
