"""Refund rows. The only writer of reversing credits besides the webhook ingest path."""

from __future__ import annotations

import sqlite3

from core.db import utcnow
from core.drivers import Refund
from core.ids import new_id


def apply_refund(conn: sqlite3.Connection, refund: Refund, *, source: str = "refund") -> str:
    """Idempotent. Inserts a credit and links it via reversed_by when the original exists."""
    existing = conn.execute(
        "SELECT id FROM transactions WHERE external_id=?",
        (refund.id,),
    ).fetchone()
    if existing:
        return existing["id"]
    orig = conn.execute(
        "SELECT id, venture_id FROM transactions WHERE external_id=?",
        (refund.charge_id,),
    ).fetchone()
    tx_id = new_id("TX")
    conn.execute(
        """INSERT INTO transactions(
               id, venture_id, intent_id, direction, amount_cents, currency,
               category, source, external_id, occurred_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            tx_id,
            orig["venture_id"] if orig else None,
            None,
            "credit",
            int(refund.amount_cents),
            "USD",
            "refund",
            source,
            refund.id,
            refund.occurred_at or utcnow(),
        ),
    )
    if orig:
        conn.execute(
            "UPDATE transactions SET reversed_by=? WHERE id=?",
            (tx_id, orig["id"]),
        )
    return tx_id
