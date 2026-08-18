from __future__ import annotations

from datetime import UTC, datetime

from core.db import connect, utcnow
from core.paths import Paths

HEARTBEAT_GAP_SECONDS = 900


def beat(paths: Paths, service: str) -> None:
    if not paths.db.exists():
        return
    conn = connect(paths.db)
    try:
        conn.execute("INSERT INTO heartbeats(service, at) VALUES (?, ?)", (service, utcnow()))
        conn.commit()
    finally:
        conn.close()


def missed_heartbeats(paths: Paths, gap_seconds: int = HEARTBEAT_GAP_SECONDS) -> list[tuple[str, float]]:
    """Services that have beaten at least once and then gone silent for gap_seconds."""
    if not paths.db.exists():
        return []
    conn = connect(paths.db)
    try:
        rows = conn.execute("SELECT service, MAX(at) FROM heartbeats GROUP BY service").fetchall()
    finally:
        conn.close()
    now = datetime.now(UTC)
    out: list[tuple[str, float]] = []
    for service, at in rows:
        if not at:
            continue
        try:
            ts = datetime.fromisoformat(str(at))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        except ValueError:
            continue
        age = (now - ts).total_seconds()
        if age >= gap_seconds:
            out.append((str(service), age))
    return out
