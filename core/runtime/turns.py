"""File-backed turn queue. The agent never opens SQLite; crash recovery is these files."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from core.ids import new_id
from core.paths import Paths

LEASE_SECONDS = 300
TURN_PROVENANCE_TTL_SECONDS = 600


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _later(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=int(seconds))).replace(microsecond=0).isoformat()


def turns_dir(paths: Paths):
    dest = paths.runtime / "turns"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def enqueue(paths: Paths, payload: dict[str, Any], *, session_id: str = "") -> dict[str, Any]:
    existing = find_open(paths, session_id) if session_id else None
    if existing:
        existing["payload"] = payload
        existing["updated_at"] = _now()
        _write(paths, existing)
        return existing
    turn = {
        "id": new_id("TN"),
        "session_id": session_id,
        "status": "pending",
        "payload": payload,
        "attempts": 0,
        "lease_until": None,
        "available_at": _now(),
        "last_error": None,
        "provenance": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write(paths, turn)
    return turn


def find_open(paths: Paths, session_id: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    for turn in list_turns(paths):
        if turn.get("session_id") == session_id and turn.get("status") in {"pending", "leased"}:
            return turn
    return None


def list_turns(paths: Paths) -> list[dict[str, Any]]:
    out = []
    for path in sorted(turns_dir(paths).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def recover(paths: Paths) -> int:
    """Expired leases become pending so a crash mid-turn does not lose the work."""
    expire_stale_turns(paths)
    now = _now()
    n = 0
    for turn in list_turns(paths):
        if turn.get("status") != "leased":
            continue
        until = turn.get("lease_until") or ""
        if until and until > now:
            continue
        turn["status"] = "pending"
        turn["lease_until"] = None
        turn["updated_at"] = now
        turn["last_error"] = turn.get("last_error") or "lease expired after crash"
        _write(paths, turn)
        n += 1
    return n


def claim(paths: Paths, actor: str = "core", lease_seconds: int = LEASE_SECONDS) -> dict[str, Any] | None:
    recover(paths)
    now = _now()
    pending = [
        t
        for t in list_turns(paths)
        if t.get("status") == "pending" and (t.get("available_at") or "") <= now
    ]
    pending.sort(key=lambda t: t.get("created_at") or "")
    if not pending:
        return None
    turn = pending[0]
    turn["status"] = "leased"
    turn["attempts"] = int(turn.get("attempts") or 0) + 1
    turn["lease_until"] = _later(lease_seconds)
    turn["claimed_by"] = actor
    turn["updated_at"] = now
    _write(paths, turn)
    return turn


def heartbeat(paths: Paths, turn_id: str, lease_seconds: int = LEASE_SECONDS) -> None:
    turn = _read(paths, turn_id)
    if not turn or turn.get("status") != "leased":
        return
    turn["lease_until"] = _later(lease_seconds)
    turn["updated_at"] = _now()
    _write(paths, turn)


def complete(paths: Paths, turn_id: str) -> None:
    turn = _read(paths, turn_id)
    if not turn:
        return
    turn["status"] = "done"
    turn["lease_until"] = None
    turn["provenance"] = []
    turn["updated_at"] = _now()
    _write(paths, turn)


def expire_stale_turns(paths: Paths, *, ttl_seconds: int = TURN_PROVENANCE_TTL_SECONDS) -> int:
    """Close old open turns and drop provenance so it cannot bleed across sessions."""
    now_dt = datetime.now(UTC)
    n = 0
    for turn in list_turns(paths):
        if turn.get("status") not in {"pending", "leased"}:
            continue
        updated_raw = turn.get("updated_at") or turn.get("created_at") or ""
        try:
            updated = datetime.fromisoformat(str(updated_raw))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
        except ValueError:
            updated = now_dt
        age = (now_dt - updated).total_seconds()
        lease_until = turn.get("lease_until")
        lease_expired = bool(lease_until and str(lease_until) <= _now())
        if age >= ttl_seconds or (turn.get("status") == "leased" and lease_expired and age >= LEASE_SECONDS):
            turn["status"] = "done"
            turn["lease_until"] = None
            turn["provenance"] = []
            turn["last_error"] = turn.get("last_error") or "turn expired; provenance cleared"
            turn["updated_at"] = _now()
            _write(paths, turn)
            n += 1
    return n


def fail(paths: Paths, turn_id: str, error: str, *, retryable: bool = True, backoff_seconds: int = 30) -> None:
    turn = _read(paths, turn_id)
    if not turn:
        return
    turn["last_error"] = error
    turn["updated_at"] = _now()
    if retryable:
        turn["status"] = "pending"
        turn["lease_until"] = None
        turn["available_at"] = _later(backoff_seconds)
    else:
        turn["status"] = "failed"
        turn["lease_until"] = None
    _write(paths, turn)


def attach_provenance(paths: Paths, session_id: str, provenance: dict[str, Any]) -> None:
    turn = find_open(paths, session_id)
    if not turn:
        return
    items = [p for p in (turn.get("provenance") or []) if isinstance(p, dict)]
    if provenance not in items:
        items.append(provenance)
    turn["provenance"] = items
    turn["updated_at"] = _now()
    _write(paths, turn)


def set_channel(paths: Paths, session_id: str, slug: str) -> None:
    turn = find_open(paths, session_id)
    if not turn:
        return
    turn["channel"] = slug
    turn["updated_at"] = _now()
    _write(paths, turn)


def record_hook(paths: Paths, payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    body = {
        "hook": payload.get("hook_event_name"),
        "user_message": extra.get("user_message") or payload.get("user_message"),
        "cwd": payload.get("cwd"),
    }
    turn = enqueue(paths, body, session_id=session_id)
    if payload.get("hook_event_name") in {"pre_llm_call", "post_tool_call"}:
        if turn.get("status") == "pending":
            turn["status"] = "leased"
            turn["attempts"] = int(turn.get("attempts") or 0) + 1
            turn["lease_until"] = _later(LEASE_SECONDS)
            turn["claimed_by"] = "hermes"
            turn["updated_at"] = _now()
            _write(paths, turn)
        else:
            heartbeat(paths, turn["id"])
    return turn


def _path(paths: Paths, turn_id: str):
    return turns_dir(paths) / f"{turn_id}.json"


def _read(paths: Paths, turn_id: str) -> dict[str, Any] | None:
    path = _path(paths, turn_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(paths: Paths, turn: dict[str, Any]) -> None:
    path = _path(paths, turn["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(turn), encoding="utf-8")
    tmp.replace(path)
