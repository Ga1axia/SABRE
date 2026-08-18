from __future__ import annotations

import argparse
from types import SimpleNamespace

from core.cli.commands import upgrade as upgrade_cmd
from core.setup.doctor import Report, CheckResult


def test_upgrade_rolls_back_git_and_snapshot_on_doctor_failure(sabre_home, monkeypatch, tmp_path):
    app = sabre_home.app
    app.mkdir(parents=True, exist_ok=True)
    (app / ".git").mkdir()
    monkeypatch.setattr("core.cli.commands.upgrade.repo_root", lambda: app)
    monkeypatch.setattr("core.cli.commands.upgrade.load_env", lambda _p: None)
    monkeypatch.setattr("core.cli.commands.upgrade.load_settings", lambda _p: SimpleNamespace())
    monkeypatch.setattr("core.cli.commands.upgrade.stop_all", lambda _s: None)
    monkeypatch.setattr("core.cli.commands.upgrade.start_all", lambda _s: None)
    monkeypatch.setattr("core.cli.commands.upgrade.create_backup", lambda _p: sabre_home.backups / "snap.tar.gz")
    monkeypatch.setattr("core.cli.commands.upgrade.prior_rollback_ref", lambda _a: "v0.1.0-pre-remediation")

    rolled: list[str] = []
    restored: list[str] = []

    monkeypatch.setattr("core.cli.commands.upgrade.checkout_ref", lambda _a, ref: rolled.append(ref))
    monkeypatch.setattr(
        "core.cli.commands.upgrade.restore_backup",
        lambda _p, snap: restored.append(snap),
    )
    monkeypatch.setattr(
        "core.setup.doctor.run_doctor",
        lambda _p: Report([CheckResult("x", "fatal", False, "broken", "")]),
    )
    monkeypatch.setattr("core.cli.commands.upgrade.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0))

    rc = upgrade_cmd.run(argparse.Namespace(ref=None))
    assert rc == 1
    assert rolled == ["v0.1.0-pre-remediation"]
    assert restored == [str(sabre_home.backups / "snap.tar.gz")]
