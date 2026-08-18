"""Persist undelivered critical alerts for retry on startup."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from core.db import utcnow
from core.paths import Paths

MAX_ATTEMPTS = 5
BASE_BACKOFF = 2.0


def queue_path(paths: Paths):
    paths.runtime.mkdir(parents=True, exist_ok=True)
    return paths.runtime / "alert-queue.jsonl"


def enqueue(paths: Paths, row: dict[str, Any]) -> None:
    payload = {
        "at": utcnow(),
        "attempts": 0,
        **row,
    }
    with queue_path(paths).open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _read_all(paths: Paths) -> list[dict[str, Any]]:
    path = queue_path(paths)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def _write_all(paths: Paths, rows: list[dict[str, Any]]) -> None:
    path = queue_path(paths)
    if not rows:
        path.unlink(missing_ok=True)
        return
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def drain(
    paths: Paths,
    deliver: Callable[[dict[str, Any]], bool],
    *,
    now: float | None = None,
) -> int:
    """Retry queued alerts. Returns count delivered."""
    ts = time.monotonic() if now is None else now
    pending = _read_all(paths)
    if not pending:
        return 0
    kept: list[dict[str, Any]] = []
    delivered = 0
    for row in pending:
        attempts = int(row.get("attempts") or 0)
        next_at = float(row.get("next_at") or 0)
        if next_at and ts < next_at:
            kept.append(row)
            continue
        if deliver(row):
            delivered += 1
            continue
        attempts += 1
        row["attempts"] = attempts
        row["last_at"] = utcnow()
        if attempts >= MAX_ATTEMPTS:
            _dead_letter(paths, row)
            continue
        row["next_at"] = ts + min(BASE_BACKOFF * (2 ** (attempts - 1)), 300.0)
        kept.append(row)
    _write_all(paths, kept)
    return delivered


def _dead_letter(paths: Paths, row: dict[str, Any]) -> None:
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        with (paths.logs / "alert-undelivered.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": utcnow(), "queue_exhausted": True, **row}) + "\n")
    except OSError:
        pass
