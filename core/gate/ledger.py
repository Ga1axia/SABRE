"""Ledger helpers used by the gate. Agent never imports this."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.db import later, utcnow
from core.gate.classify import LedgerView
from core.ids import new_id
from core.paths import Paths


def spend_frozen(paths: Paths) -> bool:
    report = paths.home / "reconcile-last.json"
    if not report.exists():
        return False
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(data.get("divergences"))


def ledger_view(conn: sqlite3.Connection, venture_id: str | None = None) -> LedgerView:
    today = utcnow()[:10]
    month = utcnow()[:7]
    spend_today = conn.execute(
        "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit' AND occurred_at LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]
    spend_month = conn.execute(
        "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit' AND occurred_at LIKE ?",
        (f"{month}%",),
    ).fetchone()[0]
    spend_v = 0
    if venture_id:
        spend_v = conn.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit' AND venture_id=?",
            (venture_id,),
        ).fetchone()[0]
    accounts = {r[0] for r in conn.execute("SELECT id FROM accounts WHERE status='active'")}
    platforms = {r[0] for r in conn.execute("SELECT DISTINCT platform FROM accounts")}
    rates: dict[tuple[str, str], int] = {}
    for row in conn.execute(
        "SELECT account_id, action, count FROM rate_usage WHERE window_date=?",
        (today,),
    ):
        rates[(row[0], row[1])] = row[2]
    return LedgerView(
        spend_today_cents=int(spend_today),
        spend_month_cents=int(spend_month),
        spend_venture_cents=int(spend_v),
        rate_counts=rates,
        account_ids=accounts,
        known_platforms=platforms,
    )


def insert_intent(
    conn: sqlite3.Connection,
    intent: dict[str, Any],
    classification: str,
    state: str,
    hold_until: str | None = None,
) -> str:
    existing = conn.execute(
        "SELECT id, classification, state FROM intents WHERE idempotency_key=?",
        (intent["idempotency_key"],),
    ).fetchone()
    if existing:
        return existing["id"]
    iid = new_id("I")
    venture_ref = intent.get("venture_id") or intent.get("venture")
    venture_id = None
    if venture_ref:
        found = conn.execute(
            "SELECT id FROM ventures WHERE id=? OR slug=?",
            (venture_ref, venture_ref),
        ).fetchone()
        venture_id = found["id"] if found else None
    conn.execute(
        """INSERT INTO intents(
            id, venture_id, task_id, kind, classification, payload, idempotency_key,
            rationale, dissent, provenance, state, hold_until, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            iid,
            venture_id,
            intent.get("task_id"),
            intent["kind"],
            classification,
            json.dumps(intent.get("payload") or {}),
            intent["idempotency_key"],
            intent.get("rationale") or "",
            intent.get("dissent"),
            json.dumps(intent.get("provenance") or []),
            state,
            hold_until,
            utcnow(),
        ),
    )
    return iid


def get_intent_by_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM intents WHERE idempotency_key=?", (key,)).fetchone()


def claim_task(conn: sqlite3.Connection, task_id: str, actor: str, lease_seconds: int = 900) -> bool:
    now = utcnow()
    until = later(lease_seconds, now)
    cur = conn.execute(
        """UPDATE tasks SET status='in-progress', claimed_by=?, lease_until=?
           WHERE id=? AND (claimed_by IS NULL OR lease_until IS NULL OR lease_until < ?)""",
        (actor, until, task_id, now),
    )
    return cur.rowcount == 1


def expire_held_red(conn: sqlite3.Connection, days: int, now: str | None = None) -> int:
    now = now or utcnow()
    cutoff = later(-int(days) * 86400, now)
    cur = conn.execute(
        """UPDATE intents SET state='expired'
           WHERE classification='red' AND state='held'
             AND (
               (hold_until IS NOT NULL AND hold_until <= ?)
               OR (hold_until IS NULL AND created_at <= ?)
             )""",
        (now, cutoff),
    )
    return int(cur.rowcount or 0)
