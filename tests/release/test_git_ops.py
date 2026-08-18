from __future__ import annotations

import subprocess
from pathlib import Path

from core.release.git_ops import checkout_ref, current_head, merge_with_health_rollback, prior_rollback_ref


def _git(args: list[str], cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr or r.stdout


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "test"], repo)
    (repo / "ok.txt").write_text("ok\n", encoding="utf-8")
    _git(["add", "ok.txt"], repo)
    _git(["commit", "-m", "baseline"], repo)
    _git(["tag", "v0.1.0-pre-remediation"], repo)
    return repo


def test_prior_rollback_ref_returns_nearest_tag(tmp_path):
    repo = _init_repo(tmp_path)
    assert prior_rollback_ref(repo) == "v0.1.0-pre-remediation"


def test_merge_rolls_back_on_failed_health(tmp_path):
    repo = _init_repo(tmp_path)
    before = current_head(repo)
    _git(["checkout", "-b", "feature"], repo)
    (repo / "ok.txt").write_text("broken\n", encoding="utf-8")
    _git(["commit", "-am", "break"], repo)
    _git(["checkout", "main"], repo)
    outcome, head = merge_with_health_rollback(repo, "feature", lambda: False)
    assert outcome == "rolled_back"
    assert head == before
    assert (repo / "ok.txt").read_text(encoding="utf-8") == "ok\n"


def test_merge_keeps_change_on_passing_health(tmp_path):
    repo = _init_repo(tmp_path)
    _git(["checkout", "-b", "feature"], repo)
    (repo / "ok.txt").write_text("better\n", encoding="utf-8")
    _git(["commit", "-am", "improve"], repo)
    _git(["checkout", "main"], repo)
    outcome, _head = merge_with_health_rollback(repo, "feature", lambda: True)
    assert outcome == "merged"
    assert (repo / "ok.txt").read_text(encoding="utf-8") == "better\n"


def test_checkout_ref_restores_tag(tmp_path):
    repo = _init_repo(tmp_path)
    tagged = current_head(repo)
    _git(["checkout", "-b", "feature"], repo)
    (repo / "ok.txt").write_text("broken\n", encoding="utf-8")
    _git(["commit", "-am", "break"], repo)
    checkout_ref(repo, "v0.1.0-pre-remediation")
    assert current_head(repo) == tagged
