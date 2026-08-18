"""Gate-side economic loop: board sync, claim, kill sweep, promotion."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import Settings
from core.db import utcnow
from core.gate.ledger import claim_task
from core.ids import new_id
from core.loop.board import lint_delegation, pick_ready, write_task
from core.paths import Paths

ACTIVE = {"ideating", "building", "launched", "earning", "stalled"}


def tick(settings: Settings, conn: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    paths = settings.paths
    incoming = body.get("tasks") if isinstance(body.get("tasks"), list) else []
    _expire_leases(conn)
    for task in incoming:
        if not isinstance(task, dict):
            continue
        if lint_delegation(task):
            continue
        _upsert_task(conn, task)
    rows = [dict(r) for r in conn.execute("SELECT * FROM tasks WHERE status='ready'")]
    ready = pick_ready(
        [
            {
                "id": r["id"],
                "status": r["status"],
                "priority": _priority_from_team(r),
                "opened": r["created_at"],
                "goal": r["goal"],
                "acceptance": r["acceptance"],
            }
            for r in rows
        ]
    )
    if ready is None:
        return {"ok": True, "claimed": None}
    actor = str(body.get("actor") or "core")
    if not claim_task(conn, ready["id"], actor, settings.task_lease_seconds):
        return {"ok": True, "claimed": None}
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (ready["id"],)).fetchone()
    claimed = dict(row) if row else {"id": ready["id"], "status": "in-progress"}
    claimed["priority"] = ready.get("priority") or "medium"
    try:
        existing = {}
        path = paths.work / "board" / f"{claimed['id']}.md"
        if path.exists():
            from core.loop.board import parse_task

            existing = parse_task(path.read_text(encoding="utf-8"))
        write_task(paths, {**existing, **claimed, "status": "in-progress"})
    except Exception:
        pass
    return {"ok": True, "claimed": claimed}


def kill_sweep(settings: Settings, conn: sqlite3.Connection) -> dict[str, Any]:
    now = datetime.now(UTC)
    killed: list[dict[str, str]] = []
    rows = conn.execute("SELECT * FROM ventures WHERE status != 'killed'").fetchall()
    for row in rows:
        v = dict(row)
        reasons = _kill_reasons(conn, v, now)
        if not reasons:
            continue
        reason = "; ".join(reasons)
        conn.execute(
            "UPDATE ventures SET status='killed', close_reason=?, closed_at=? WHERE id=?",
            (reason, utcnow(), v["id"]),
        )
        pid = new_id("PM")
        conn.execute(
            """INSERT INTO postmortems(id, venture_id, believed, did, happened, earliest_signal, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                pid,
                v["id"],
                v.get("thesis") or "",
                "kill sweep (gate-enforced)",
                reason,
                reasons[0],
                utcnow(),
            ),
        )
        if v.get("card_id"):
            conn.execute("UPDATE cards SET status='frozen' WHERE id=?", (v["card_id"],))
        killed.append({"id": v["id"], "slug": v.get("slug") or "", "reason": reason, "postmortem_id": pid})
    return {"ok": True, "killed": killed}


def promote(settings: Settings, conn: sqlite3.Connection) -> dict[str, Any]:
    paths = settings.paths
    uses = _load_skill_ventures(paths)
    promoted: list[str] = []
    retired: list[str] = []
    for sid, by_venture in uses.items():
        if len(by_venture) < 2:
            continue
        nets = list(by_venture.values())
        row = conn.execute("SELECT id, name, status FROM skills WHERE id=?", (sid,)).fetchone()
        if not row:
            continue
        if all(int(n) >= 0 for n in nets):
            conn.execute(
                "UPDATE skills SET status='promoted', promoted_at=? WHERE id=?",
                (utcnow(), sid),
            )
            promoted.append(sid)
        elif all(int(n) < 0 for n in nets):
            conn.execute(
                "UPDATE skills SET status='retired', retired_at=?, retire_reason=? WHERE id=?",
                (utcnow(), "negative contribution in two ventures", sid),
            )
            _anti_playbook(paths, f"Retired skill {row['name']}: negative net in {len(by_venture)} ventures.")
            retired.append(sid)
    lesson_promoted = _promote_lessons(conn)
    return {"ok": True, "promoted": promoted, "retired": retired, "lessons_promoted": lesson_promoted}


def record_skill_venture(paths: Paths, skill_id: str, venture_id: str, net_cents: int) -> None:
    data = _load_skill_ventures(paths)
    slot = data.setdefault(skill_id, {})
    slot[venture_id] = int(net_cents)
    dest = paths.runtime / "skill-ventures.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def venture_net_cents(conn: sqlite3.Connection, venture_id: str) -> int:
    rev = conn.execute(
        """SELECT COALESCE(SUM(amount_cents),0) FROM transactions
           WHERE direction='credit' AND category='revenue' AND venture_id=?""",
        (venture_id,),
    ).fetchone()[0]
    spend = conn.execute(
        "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit' AND venture_id=?",
        (venture_id,),
    ).fetchone()[0]
    inf = conn.execute(
        "SELECT COALESCE(SUM(cost_cents),0) FROM events WHERE venture_id=?",
        (venture_id,),
    ).fetchone()[0]
    return int(rev) - int(spend) - int(inf or 0)


def concurrent_ventures(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        f"SELECT COUNT(*) FROM ventures WHERE status IN ({','.join('?' * len(ACTIVE))})",
        tuple(ACTIVE),
    ).fetchone()
    return int(row[0])


def _team_blob(task: dict[str, Any]) -> str:
    team = task.get("team") or []
    if isinstance(team, str):
        try:
            team = json.loads(team)
        except json.JSONDecodeError:
            team = [team]
    if isinstance(team, dict):
        data = dict(team)
        data["priority"] = task.get("priority") or data.get("priority") or "medium"
        return json.dumps(data)
    return json.dumps({"priority": task.get("priority") or "medium", "members": team})


def _upsert_task(conn: sqlite3.Connection, task: dict[str, Any]) -> None:
    tid = str(task.get("id") or new_id("T"))
    existing = conn.execute("SELECT id FROM tasks WHERE id=?", (tid,)).fetchone()
    blob = _team_blob(task)
    if existing:
        conn.execute(
            "UPDATE tasks SET goal=?, acceptance=?, team=?, status=? WHERE id=? AND claimed_by IS NULL",
            (
                task.get("goal") or "",
                task.get("acceptance") or "",
                blob,
                task.get("status") or "ready",
                tid,
            ),
        )
        return
    conn.execute(
        """INSERT INTO tasks(id, venture_id, parent_id, goal, acceptance, team, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            tid,
            task.get("venture_id") or task.get("venture"),
            task.get("parent_id"),
            task.get("goal") or "",
            task.get("acceptance") or "",
            blob,
            task.get("status") or "ready",
            task.get("opened") or utcnow(),
        ),
    )


def _expire_leases(conn: sqlite3.Connection) -> None:
    now = utcnow()
    conn.execute(
        """UPDATE tasks SET status='ready', claimed_by=NULL, lease_until=NULL
           WHERE status='in-progress' AND lease_until IS NOT NULL AND lease_until < ?""",
        (now,),
    )


def _priority_from_team(row: sqlite3.Row | dict[str, Any]) -> str:
    raw = row["team"] if not isinstance(row, dict) else row.get("team")
    if isinstance(raw, str) and raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("priority"):
                return str(data["priority"])
        except json.JSONDecodeError:
            pass
    # Priority lives on the file; DB team JSON may include it as last resort.
    return "medium"


def _kill_reasons(conn: sqlite3.Connection, v: dict[str, Any], now: datetime) -> list[str]:
    try:
        criteria = json.loads(v.get("kill_criteria") or "{}")
    except json.JSONDecodeError:
        criteria = {}
    if not isinstance(criteria, dict):
        criteria = {}
    vid = v["id"]
    spend = int(
        conn.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit' AND venture_id=?",
            (vid,),
        ).fetchone()[0]
    )
    rev = int(
        conn.execute(
            """SELECT COALESCE(SUM(amount_cents),0) FROM transactions
               WHERE direction='credit' AND category='revenue' AND venture_id=?""",
            (vid,),
        ).fetchone()[0]
    )
    created = _parse_ts(v.get("created_at") or utcnow())
    days = max(0, (now - created).days)
    spend_cap = int(criteria.get("no_revenue_spend_cents") or 15000)
    day_cap = int(criteria.get("no_revenue_days") or 21)
    reasons: list[str] = []
    if rev <= 0 and spend >= spend_cap:
        reasons.append(f"no revenue after ${spend_cap / 100:.0f} spend")
    if rev <= 0 and days >= day_cap:
        reasons.append(f"no revenue after {day_cap} days")
    if criteria.get("legal_event_fired"):
        reasons.append("legal/ToS/platform event")
    weeks = int(criteria.get("negative_weeks_after_revenue") or 3)
    if rev > 0 and _negative_streak(conn, vid, weeks):
        reasons.append(f"negative net {weeks} consecutive weeks after first revenue")
    return reasons


def _negative_streak(conn: sqlite3.Connection, vid: str, weeks: int) -> bool:
    first = conn.execute(
        """SELECT MIN(occurred_at) FROM transactions
           WHERE venture_id=? AND direction='credit' AND category='revenue'""",
        (vid,),
    ).fetchone()[0]
    if not first:
        return False
    start = _parse_ts(first)
    nets: list[int] = []
    for i in range(weeks):
        a = start + timedelta(days=7 * i)
        b = a + timedelta(days=7)
        rev = conn.execute(
            """SELECT COALESCE(SUM(amount_cents),0) FROM transactions
               WHERE venture_id=? AND direction='credit' AND category='revenue'
                 AND occurred_at>=? AND occurred_at<?""",
            (vid, a.isoformat(), b.isoformat()),
        ).fetchone()[0]
        spend = conn.execute(
            """SELECT COALESCE(SUM(amount_cents),0) FROM transactions
               WHERE venture_id=? AND direction='debit'
                 AND occurred_at>=? AND occurred_at<?""",
            (vid, a.isoformat(), b.isoformat()),
        ).fetchone()[0]
        nets.append(int(rev) - int(spend))
    return len(nets) >= weeks and all(n < 0 for n in nets)


def _parse_ts(raw: str) -> datetime:
    text = str(raw).replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def _load_skill_ventures(paths: Paths) -> dict[str, dict[str, int]]:
    path = paths.runtime / "skill-ventures.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for sid, by_v in data.items():
        if isinstance(by_v, dict):
            out[str(sid)] = {str(k): int(v) for k, v in by_v.items()}
    return out


def _promote_lessons(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT id, rule, venture_id, status FROM lessons WHERE status='candidate'").fetchall()
    by_rule: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_rule.setdefault(str(row["rule"]), []).append(row)
    promoted: list[str] = []
    for _rule, group in by_rule.items():
        ventures = {r["venture_id"] for r in group if r["venture_id"]}
        if len(ventures) < 2:
            continue
        if any(venture_net_cents(conn, vid) < 0 for vid in ventures):
            continue
        ids = [r["id"] for r in group]
        conn.execute(
            f"UPDATE lessons SET status='promoted' WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        promoted.extend(ids)
    return promoted


def _anti_playbook(paths: Paths, line: str) -> None:
    path = paths.work / "COMPANY.md"
    stamp = utcnow()[:10]
    entry = f"\n- {stamp}: {line}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Anti-playbook\n" + entry, encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    marker = "# Anti-playbook"
    if marker in text:
        text = text.replace(marker, marker + entry, 1)
    else:
        text = text.rstrip() + "\n\n" + marker + entry
    path.write_text(text, encoding="utf-8")
