"""PRD §23 Phase 0: install.sh, CLI, three OS users. sabre cannot read operator home."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from core.setup.checks import _isolation_read, check_iso_home
from core.setup.steps import os_users


def test_isolation_read_on_directory_is_unproven(tmp_path, monkeypatch):
    """head(1) on a directory exits non-zero. That is not an isolation proof."""
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr("core.setup.checks.is_dev", lambda: False)

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Is a directory")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # True = agent can read OR proof failed closed (unproven). False = proved cannot read.
    assert _isolation_read("sabre", tmp_path) is True


def test_isolation_read_denied_on_file_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr("core.setup.checks.is_dev", lambda: False)
    probe = tmp_path / "operator-secret"
    probe.write_text("do-not-read\n", encoding="utf-8")

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _isolation_read("sabre", probe) is False


def test_check_iso_home_probes_a_regular_file(sabre_home, monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr("core.setup.checks.is_dev", lambda: False)
    home = tmp_path / "operator"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    seen: list[Path] = []

    def fake_run(args, **kwargs):
        seen.append(Path(args[-1]))
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    settings = SimpleNamespace(agent_user="sabre")
    ok, _msg = check_iso_home(sabre_home, settings)
    assert seen, "isolation.home must attempt a read"
    assert all(p.is_file() for p in seen)
    assert ok is True


def test_os_users_verify_does_not_pass_without_proof(sabre_home, monkeypatch):
    monkeypatch.setattr(os_users, "is_dev", lambda: False)
    monkeypatch.setattr(os_users, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(os_users, "_user_exists", lambda name: name in {"sabre", "sabre-gate"})
    monkeypatch.setattr(
        "core.setup.checks.check_iso_home",
        lambda paths, settings: (False, "agent user can read operator home (or isolation unproven)"),
    )
    ctx = {"paths": sabre_home, "settings": SimpleNamespace(agent_user="sabre")}
    err = os_users.verify(ctx)
    assert err is not None
    assert "unproven" in err.lower() or "read" in err.lower()
