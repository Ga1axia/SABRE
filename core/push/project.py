"""Project a redacted snapshot. Never a database dump."""

from __future__ import annotations

from typing import Any

from core.config import Settings
from core.db import connect


def project(settings: Settings) -> dict[str, Any]:
    paths = settings.paths
    snap: dict[str, Any] = {
        "topology": settings.topology,
        "no_spend": settings.no_spend,
        "envelopes": settings.envelopes,
        "ventures": [],
        "transactions": [],
        "events": [],
        "accounts": [],
        "outreach": {"counts": {}, "outcomes": {}},
    }
    if not paths.db.exists():
        return snap
    conn = connect(paths.db)
    try:
        snap["ventures"] = [
            {
                "slug": r["slug"],
                "name": r["name"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in conn.execute("SELECT slug, name, status, created_at FROM ventures")
        ]
        snap["transactions"] = [
            {
                "amount_cents": r["amount_cents"],
                "category": r["category"],
                "venture_id": r["venture_id"],
                "direction": r["direction"],
                "occurred_at": r["occurred_at"],
            }
            for r in conn.execute(
                """SELECT amount_cents, category, venture_id, direction, occurred_at
                   FROM transactions ORDER BY occurred_at DESC LIMIT 100"""
            )
        ]
        snap["events"] = [
            {
                "tool": r["tool"],
                "status": r["status"],
                "duration_ms": r["duration_ms"],
                "occurred_at": r["occurred_at"],
            }
            for r in conn.execute(
                "SELECT tool, status, duration_ms, occurred_at FROM events ORDER BY id DESC LIMIT 50"
            )
        ]
        snap["accounts"] = [
            {"platform": r["platform"], "status": r["status"]}
            for r in conn.execute("SELECT platform, status FROM accounts")
        ]
    finally:
        conn.close()
    return snap
