"""Hermes v0.20.1 cron jobs. Jobs live in HERMES_HOME/cron/jobs.json, not config.yaml."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.paths import Paths, core_dir, repo_root

HERMES_VERSION = "0.20.1"

# Runtime fields Hermes mutates. Keep them across layout rewrites for the same id.
_PRESERVE = (
    "last_run_at",
    "last_status",
    "last_error",
    "last_delivery_error",
    "next_run_at",
    "created_at",
    "paused_at",
    "paused_reason",
    "state",
    "monitor_state",
)

EXPECTED_JOBS: tuple[dict[str, Any], ...] = (
    {
        "id": "sabre-main-loop",
        "name": "main-loop",
        "command": "tick",
        "script": "sabre_tick.py",
        "schedule": {"kind": "interval", "minutes": 30, "display": "every 30m"},
    },
    {
        "id": "sabre-opportunity-scan",
        "name": "opportunity-scan",
        "command": "scan",
        "script": "sabre_scan.py",
        "schedule": {"kind": "cron", "expr": "0 6 * * *", "display": "0 6 * * *"},
    },
    {
        "id": "sabre-kill-sweep",
        "name": "kill-sweep",
        "command": "kill",
        "script": "sabre_kill.py",
        "schedule": {"kind": "cron", "expr": "0 9 * * *", "display": "0 9 * * *"},
    },
    {
        "id": "sabre-reconcile",
        "name": "reconcile",
        "command": "reconcile",
        "script": "sabre_reconcile.py",
        "schedule": {"kind": "cron", "expr": "0 2 * * *", "display": "0 2 * * *"},
    },
    {
        "id": "sabre-promote",
        "name": "promote",
        "command": "promote",
        "script": "sabre_promote.py",
        "schedule": {"kind": "cron", "expr": "0 8 * * 1", "display": "0 8 * * 1"},
    },
    {
        "id": "sabre-status-digest",
        "name": "status-digest",
        "command": "digest",
        "script": "sabre_digest.py",
        "schedule": {"kind": "cron", "expr": "0 8 * * *", "display": "0 8 * * *"},
    },
    {
        "id": "sabre-heartbeat",
        "name": "heartbeat",
        "command": "heartbeat",
        "script": "sabre_heartbeat.py",
        "schedule": {"kind": "interval", "minutes": 5, "display": "every 5m"},
    },
)

EXPECTED_JOB_NAMES = tuple(job["name"] for job in EXPECTED_JOBS)


@lru_cache(maxsize=1)
def load_jobs_schema() -> dict[str, Any]:
    path = core_dir() / "runtime" / "hermes_v0_20_1_jobs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def jobs_path(home: Path) -> Path:
    return home / "cron" / "jobs.json"


def validate_jobs_document(data: Any) -> list[str]:
    """Return schema errors. Empty means the document matches the vendored v0.20.1 shape."""
    schema = load_jobs_schema()
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"jobs.json must be an object, got {type(data).__name__}"]
    for key in schema["file"]["required"]:
        if key not in data:
            errors.append(f"missing top-level {key}")
    jobs = data.get("jobs")
    if "jobs" in data and not isinstance(jobs, list):
        errors.append(f"jobs must be an array, got {type(jobs).__name__}")
        return errors
    updated = data.get("updated_at")
    if "updated_at" in data and not isinstance(updated, str):
        errors.append("updated_at must be a string")
    if not isinstance(jobs, list):
        return errors
    required = schema["job"]["required"]
    kinds = set(schema["schedule"]["kinds"])
    for i, job in enumerate(jobs):
        prefix = f"jobs[{i}]"
        if not isinstance(job, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in required:
            if field not in job:
                errors.append(f"{prefix} missing {field}")
        if job.get("no_agent") and not job.get("script"):
            errors.append(f"{prefix} no_agent requires script")
        schedule = job.get("schedule")
        if schedule is None:
            continue
        if not isinstance(schedule, dict):
            errors.append(f"{prefix}.schedule must be an object")
            continue
        kind = schedule.get("kind")
        if kind not in kinds:
            errors.append(f"{prefix}.schedule.kind must be one of {sorted(kinds)}")
        elif kind == "interval" and not isinstance(schedule.get("minutes"), int):
            errors.append(f"{prefix}.schedule.minutes must be an integer")
        elif kind == "cron" and not isinstance(schedule.get("expr"), str):
            errors.append(f"{prefix}.schedule.expr must be a string")
        elif kind == "once" and not isinstance(schedule.get("run_at"), str):
            errors.append(f"{prefix}.schedule.run_at must be a string")
        repeat = job.get("repeat")
        if repeat is not None:
            if not isinstance(repeat, dict):
                errors.append(f"{prefix}.repeat must be an object")
            elif "times" not in repeat or "completed" not in repeat:
                errors.append(f"{prefix}.repeat requires times and completed")
    return errors


def missing_expected_jobs(data: dict[str, Any]) -> list[str]:
    jobs = data.get("jobs") if isinstance(data, dict) else None
    names = {j.get("name") for j in jobs if isinstance(j, dict)} if isinstance(jobs, list) else set()
    return [name for name in EXPECTED_JOB_NAMES if name not in names]


def write_cron_jobs(hermes_dir: Path, paths: Paths) -> Path:
    """Write HERMES_HOME/scripts/*.py and cron/jobs.json. Preserve Hermes runtime fields by id."""
    scripts_dir = hermes_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    cron_dir = hermes_dir / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)
    dest = jobs_path(hermes_dir)
    existing_by_id = _load_existing(dest)
    now = datetime.now(UTC).isoformat()
    workdir = str(repo_root())
    written: list[dict[str, Any]] = []
    owned_ids = {spec["id"] for spec in EXPECTED_JOBS}
    for spec in EXPECTED_JOBS:
        _write_script(scripts_dir / spec["script"], paths, spec["command"])
        job = _job_record(spec, now, workdir)
        prior = existing_by_id.get(spec["id"])
        if isinstance(prior, dict):
            for field in _PRESERVE:
                if field in prior:
                    job[field] = prior[field]
            completed = (prior.get("repeat") or {}).get("completed")
            if isinstance(completed, int):
                job["repeat"]["completed"] = completed
        written.append(job)
    for job_id, job in existing_by_id.items():
        if job_id not in owned_ids and isinstance(job, dict):
            written.append(job)
    payload = {"jobs": written, "updated_at": now}
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def _load_existing(dest: Path) -> dict[str, dict[str, Any]]:
    if not dest.exists():
        return {}
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    jobs = data.get("jobs") if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if isinstance(job, dict) and job.get("id"):
            out[str(job["id"])] = job
    return out


def _job_record(spec: dict[str, Any], now: str, workdir: str) -> dict[str, Any]:
    schedule = dict(spec["schedule"])
    return {
        "id": spec["id"],
        "name": spec["name"],
        "prompt": "",
        "skills": [],
        "skill": None,
        "model": None,
        "provider": None,
        "provider_snapshot": None,
        "model_snapshot": None,
        "base_url": None,
        "script": spec["script"],
        "no_agent": True,
        "monitor_script": None,
        "monitor_url": None,
        "monitor_state": None,
        "context_from": None,
        "schedule": schedule,
        "schedule_display": schedule.get("display") or spec["name"],
        "repeat": {"times": None, "completed": 0},
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "created_at": now,
        "next_run_at": now,
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_delivery_error": None,
        "deliver": None,
        "origin": "sabre",
        "enabled_toolsets": [],
        "workdir": workdir,
    }


def _write_script(dest: Path, paths: Paths, command: str) -> None:
    dest.write_text(
        (
            "# Generated by write_hermes_layout. SABRE cron entry.\n"
            "from __future__ import annotations\n\n"
            "import os\n"
            "import sys\n\n"
            f"os.environ['SABRE_HOME'] = {str(paths.home)!r}\n"
            f"_ROOT = {str(repo_root())!r}\n"
            "if _ROOT not in sys.path:\n"
            "    sys.path.insert(0, _ROOT)\n\n"
            "from core.loop.__main__ import main\n\n"
            f"if __name__ == '__main__':\n"
            f"    raise SystemExit(main([{command!r}]))\n"
        ),
        encoding="utf-8",
    )
