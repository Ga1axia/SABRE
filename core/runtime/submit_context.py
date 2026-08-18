"""Active Hermes session for mechanical submit_intent provenance scoping."""

from __future__ import annotations

import json
from typing import Any

from core.db import utcnow
from core.paths import Paths


def _path(paths: Paths):
    paths.runtime.mkdir(parents=True, exist_ok=True)
    return paths.runtime / "submit-context.json"


def touch(paths: Paths, session_id: str) -> None:
    if not session_id:
        return
    _path(paths).write_text(
        json.dumps({"session_id": session_id, "at": utcnow()}),
        encoding="utf-8",
    )


def read(paths: Paths) -> dict[str, Any]:
    path = _path(paths)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def active_session_id(paths: Paths) -> str:
    return str(read(paths).get("session_id") or "")
