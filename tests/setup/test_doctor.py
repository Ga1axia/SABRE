from __future__ import annotations

from core.setup.checks import all_checks
from core.setup.doctor import CheckResult, Report, run_doctor


def test_check_ids_stable():
    ids = [c["id"] for c in all_checks()]
    assert "isolation.home" in ids
    assert "runtime.hermes" in ids
    assert "browser.profile" in ids
    assert "gate.ceiling" in ids
    assert "gate.unknown" in ids
    assert ids.count("isolation.db") == 1


def test_doctor_json(sabre_home):
    report = run_doctor(sabre_home)
    d = report.as_dict()
    assert "ok" in d
    assert "checks" in d
    by_id = {c["id"]: c for c in d["checks"]}
    assert by_id["gate.unknown"]["ok"] is True
    assert by_id["gate.ceiling"]["ok"] is True
    assert by_id["isolation.home"]["ok"] is False
    assert by_id["isolation.home"]["severity"] == "fatal"
    assert by_id["browser.profile"]["ok"] is False
    msg = by_id["browser.profile"]["message"].lower()
    assert "launch" in msg or "missing" in msg
    assert report.ok is False
    channels = by_id["slack.channels"]
    assert channels["ok"] is False
    assert channels["severity"] == "skip"
    for sid in ("sleep.disabled", "mem.headroom", "reconcile.clean"):
        row = by_id[sid]
        if row["severity"] == "skip":
            assert row["ok"] is False, f"{sid} reported skip as passed"


def test_dev_waives_only_isolation():
    isolation = CheckResult("isolation.home", "fatal", False, "unproven")
    slack = CheckResult("slack.auth", "fatal", False, "no token")
    ceiling = CheckResult("gate.ceiling", "fatal", True, "ok")
    report = Report(results=[isolation, slack, ceiling])
    assert [r.id for r in report.blocking_fatals(waive_isolation=False)] == [
        "isolation.home",
        "slack.auth",
    ]
    waived = report.blocking_fatals(waive_isolation=True)
    assert [r.id for r in waived] == ["slack.auth"]


def test_skip_is_never_ok():
    r = CheckResult("mem.headroom", "skip", False, "not sampled")
    assert r.ok is False
    assert r.skipped is True
    report = Report(results=[r])
    assert report.ok is True
    assert report.blocking_fatals() == []
