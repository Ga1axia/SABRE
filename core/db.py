"""SQLite access for the gate and CLI. The agent never imports this module."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.paths import core_dir


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def later(seconds: int, now: str | None = None) -> str:
    """ISO timestamp `seconds` after `now` (or the current instant)."""
    if now:
        base = datetime.fromisoformat(now)
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
    else:
        base = datetime.now(UTC)
    return (base + timedelta(seconds=int(seconds))).replace(microsecond=0).isoformat()


def init_schema(db_path: Path) -> None:
    schema = (core_dir() / "schema.sql").read_text(encoding="utf-8")
    conn = connect(db_path)
    try:
        conn.executescript(schema)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(id, applied_at) VALUES (?, ?)",
            ("0001_initial", utcnow()),
        )
        apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def apply_migrations(conn: sqlite3.Connection) -> None:
    mig_dir = core_dir() / "migrations"
    if not mig_dir.exists():
        return
    applied = {row[0] for row in conn.execute("SELECT id FROM schema_migrations")}
    for path in sorted(mig_dir.glob("*.sql")):
        mid = path.stem
        if mid in applied:
            continue
        sql = path.read_text(encoding="utf-8").strip()
        if sql:
            conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(id, applied_at) VALUES (?, ?)",
            (mid, utcnow()),
        )


def migration_head() -> str:
    mig_dir = core_dir() / "migrations"
    files = sorted(p.stem for p in mig_dir.glob("*.sql"))
    return files[-1] if files else "0001_initial"


def current_migration(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM schema_migrations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


@contextmanager
def db_session(db_path: Path):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
