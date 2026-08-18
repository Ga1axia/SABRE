from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.db import connect, utcnow
from core.watch.heartbeat import beat, missed_heartbeats


def test_watcher_detects_heartbeat_gap_after_sleep(sabre_home):
    beat(sabre_home, "watch")
    old = (datetime.now(UTC) - timedelta(seconds=1000)).replace(microsecond=0).isoformat()
    conn = connect(sabre_home.db)
    conn.execute("UPDATE heartbeats SET at=? WHERE service='watch'", (old,))
    conn.commit()
    conn.close()
    missed = missed_heartbeats(sabre_home, gap_seconds=900)
    services = {name for name, _age in missed}
    assert "watch" in services


def test_fresh_heartbeat_not_reported_as_missed(sabre_home):
    beat(sabre_home, "watch")
    missed = missed_heartbeats(sabre_home, gap_seconds=900)
    assert not any(name == "watch" for name, _age in missed)
