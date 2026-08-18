"""Stage A-prime 1: Hermes jobs.json is the scheduler. Behavior, not source."""

from __future__ import annotations

import json

import yaml

from core.config import load_settings
from core.runtime.hermes import hermes_home, write_hermes_layout

EXPECTED_NAMES = {
    "main-loop",
    "opportunity-scan",
    "kill-sweep",
    "reconcile",
    "promote",
    "status-digest",
    "heartbeat",
}


def _jobs_path(paths):
    return hermes_home(paths) / "cron" / "jobs.json"


def test_write_hermes_layout_writes_jobs_json(sabre_home):
    from core.runtime.hermes_jobs import validate_jobs_document

    layout = write_hermes_layout(sabre_home, load_settings(sabre_home))
    path = _jobs_path(sabre_home)
    assert path.is_file(), "HERMES_HOME/cron/jobs.json must be written at setup"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert isinstance(data.get("jobs"), list)
    names = {j.get("name") for j in data["jobs"] if isinstance(j, dict)}
    missing = EXPECTED_NAMES - names
    assert not missing, f"missing SABRE jobs: {sorted(missing)}"
    assert layout.jobs_path == path
    errors = validate_jobs_document(data)
    assert errors == [], errors


def test_doctor_fails_on_missing_job_then_passes(sabre_home):
    from core.setup.checks import check_hermes_jobs

    write_hermes_layout(sabre_home, load_settings(sabre_home))
    path = _jobs_path(sabre_home)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["jobs"] = [j for j in data["jobs"] if j.get("name") != "heartbeat"]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    ok, msg = check_hermes_jobs(sabre_home, load_settings(sabre_home))
    assert ok is False
    assert "heartbeat" in msg

    write_hermes_layout(sabre_home, load_settings(sabre_home))
    ok, msg = check_hermes_jobs(sabre_home, load_settings(sabre_home))
    assert ok is True, msg


def test_doctor_fails_if_config_cron_is_a_list(sabre_home):
    from core.setup.checks import check_hermes_cron_list

    write_hermes_layout(sabre_home, load_settings(sabre_home))
    cfg_path = hermes_home(sabre_home) / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg["cron"] = [{"name": "main-loop", "schedule": "every 30m"}]
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    ok, msg = check_hermes_cron_list(sabre_home, load_settings(sabre_home))
    assert ok is False
    assert "list" in msg.lower()

    write_hermes_layout(sabre_home, load_settings(sabre_home))
    ok, msg = check_hermes_cron_list(sabre_home, load_settings(sabre_home))
    assert ok is True, msg
