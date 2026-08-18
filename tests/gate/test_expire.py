from __future__ import annotations

from core.config import load_settings
from core.db import connect, later, utcnow
from core.gate.ledger import expire_held_red


def test_held_red_expires_after_red_expire_days(sabre_home):
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    old = later(-8 * 86400)
    conn.execute(
        """INSERT INTO intents(
               id, kind, classification, payload, idempotency_key, rationale,
               state, created_at
           ) VALUES (?,?,?,?,?,?,?,?)""",
        ("I-old", "spend", "red", "{}", "old-key", "too much", "held", old),
    )
    conn.execute(
        """INSERT INTO intents(
               id, kind, classification, payload, idempotency_key, rationale,
               state, created_at
           ) VALUES (?,?,?,?,?,?,?,?)""",
        ("I-new", "spend", "red", "{}", "new-key", "too much", "held", utcnow()),
    )
    conn.commit()
    n = expire_held_red(conn, settings.red_expire_days)
    conn.commit()
    assert n == 1
    states = {
        row["id"]: row["state"]
        for row in conn.execute("SELECT id, state FROM intents")
    }
    assert states["I-old"] == "expired"
    assert states["I-new"] == "held"
    conn.close()


def test_hold_until_deadline_expires_red(sabre_home):
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO intents(
               id, kind, classification, payload, idempotency_key, rationale,
               state, hold_until, created_at
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        ("I-due", "core_change", "red", "{}", "due-key", "core", "held", later(-1), utcnow()),
    )
    conn.commit()
    n = expire_held_red(conn, 7)
    conn.commit()
    assert n == 1
    row = conn.execute("SELECT state FROM intents WHERE id='I-due'").fetchone()
    assert row["state"] == "expired"
    conn.close()
