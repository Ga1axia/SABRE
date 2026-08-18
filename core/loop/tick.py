"""Agent-side loop entry. Talks to the gate over I1. Never opens SQLite."""

from __future__ import annotations

from typing import Any

from core.gate.client import gate_get, gate_post
from core.loop.board import list_tasks, load_task, write_task
from core.loop.discover import discover as discover_candidates
from core.loop.scan import scan as scan_opportunities
from core.paths import Paths
from core.watch.killswitch import is_killed


def tick(paths: Paths) -> dict[str, Any]:
    if is_killed(paths):
        return {"ok": False, "error": "kill switch engaged", "claimed": None}
    payload = {"tasks": list_tasks(paths)}
    result = gate_post(paths, "/v1/loop/tick", payload)
    claimed = result.get("claimed") if isinstance(result, dict) else None
    if isinstance(claimed, dict) and claimed.get("id"):
        existing = load_task(paths, str(claimed["id"])) or {}
        write_task(paths, {**existing, **claimed, "status": "in-progress"})
    return result if isinstance(result, dict) else {"error": "tick failed"}


def scan(paths: Paths) -> dict[str, Any]:
    if is_killed(paths):
        return {"ok": False, "error": "kill switch engaged"}
    promoted: set[str] = set()
    listing = gate_get(paths, "/v1/skills")
    for row in listing.get("skills") or []:
        if str(row.get("status") or "") == "promoted":
            promoted.add(str(row.get("name") or row.get("id") or ""))
    discovery = discover_candidates(paths)
    result = scan_opportunities(paths, promoted)
    result["discovery"] = discovery
    result["ok"] = True
    return result


def kill_sweep(paths: Paths) -> dict[str, Any]:
    return gate_post(paths, "/v1/loop/kill-sweep", {})


def promote(paths: Paths) -> dict[str, Any]:
    return gate_post(paths, "/v1/loop/promote", {})


def reconcile_job(paths: Paths) -> dict[str, Any]:
    return gate_post(paths, "/v1/loop/reconcile", {})


def heartbeat(paths: Paths) -> dict[str, Any]:
    return gate_post(paths, "/v1/heartbeat", {"service": "cron"})


def status_digest(paths: Paths) -> dict[str, Any]:
    envelopes = gate_get(paths, "/v1/ledger/envelopes")
    ventures = gate_get(paths, "/v1/ledger/ventures")
    if envelopes.get("error"):
        return {"ok": False, "error": envelopes.get("error")}
    if ventures.get("error"):
        return {"ok": False, "error": ventures.get("error")}
    rows = ventures.get("ventures") or []
    active = [v for v in rows if str(v.get("status") or "") not in {"killed", "closed"}]
    env = envelopes.get("envelopes") or {}
    spend = env.get("spend") or {}
    text = (
        f"SABRE digest: {len(active)} active ventures of {len(rows)}; "
        f"no_spend={envelopes.get('no_spend')}; "
        f"daily_max={spend.get('daily_max')}; monthly_max={spend.get('monthly_max')}."
    )
    from core.watch.alert import alert

    posted = alert(paths, text, "status")
    return {"ok": True, "posted": posted, "ventures": len(rows), "active": len(active)}
