from __future__ import annotations

from core.db import connect, later, utcnow
from core.gate.ledger import claim_task


def test_claim_lease_is_in_the_future(sabre_home):
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO tasks(id, goal, acceptance, status, created_at)
           VALUES ('T-lease', 'do', 'done', 'ready', ?)""",
        (utcnow(),),
    )
    conn.commit()
    assert claim_task(conn, "T-lease", "agent-a", lease_seconds=900) is True
    row = conn.execute("SELECT claimed_by, lease_until FROM tasks WHERE id='T-lease'").fetchone()
    assert row["claimed_by"] == "agent-a"
    assert row["lease_until"] > utcnow()
    assert claim_task(conn, "T-lease", "agent-b", lease_seconds=900) is False
    still = conn.execute("SELECT claimed_by FROM tasks WHERE id='T-lease'").fetchone()
    assert still["claimed_by"] == "agent-a"
    conn.close()


def test_expired_lease_is_stealable(sabre_home):
    conn = connect(sabre_home.db)
    past = later(-60)
    conn.execute(
        """INSERT INTO tasks(id, goal, acceptance, status, claimed_by, lease_until, created_at)
           VALUES ('T-old', 'do', 'done', 'in-progress', 'agent-a', ?, ?)""",
        (past, utcnow()),
    )
    conn.commit()
    assert claim_task(conn, "T-old", "agent-b", lease_seconds=900) is True
    row = conn.execute("SELECT claimed_by FROM tasks WHERE id='T-old'").fetchone()
    assert row["claimed_by"] == "agent-b"
    conn.close()


def test_lease_expires_while_holder_still_working(sabre_home):
    """A still holds the task (never released). After lease expiry, B can steal."""
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO tasks(id, goal, acceptance, status, created_at)
           VALUES ('T-work', 'do', 'done', 'ready', ?)""",
        (utcnow(),),
    )
    conn.commit()
    assert claim_task(conn, "T-work", "agent-a", lease_seconds=900) is True
    conn.execute("UPDATE tasks SET lease_until=? WHERE id='T-work'", (later(-1),))
    conn.commit()
    working = conn.execute("SELECT status, claimed_by, result FROM tasks WHERE id='T-work'").fetchone()
    assert working["status"] == "in-progress"
    assert working["claimed_by"] == "agent-a"
    assert working["result"] is None
    assert claim_task(conn, "T-work", "agent-b", lease_seconds=900) is True
    stolen = conn.execute("SELECT claimed_by FROM tasks WHERE id='T-work'").fetchone()
    assert stolen["claimed_by"] == "agent-b"
    conn.close()
