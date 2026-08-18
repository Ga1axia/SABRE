from __future__ import annotations

import subprocess
from pathlib import Path

from core.release.self_mod import apply_core_branch


def _git(args: list[str], cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr or r.stdout


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "test"], repo)
    (repo / "health.txt").write_text("1\n", encoding="utf-8")
    _git(["add", "health.txt"], repo)
    _git(["commit", "-m", "baseline"], repo)
    return repo


def test_self_mod_merge_rolls_back_when_health_fails(tmp_path):
    repo = _init_repo(tmp_path)
    before = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    _git(["checkout", "-b", "core-change"], repo)
    (repo / "health.txt").write_text("0\n", encoding="utf-8")
    _git(["commit", "-am", "bad core change"], repo)
    _git(["checkout", "main"], repo)

    def health() -> bool:
        return (repo / "health.txt").read_text(encoding="utf-8").strip() == "1"

    outcome, head = apply_core_branch(repo, "core-change", health)
    assert outcome == "rolled_back"
    assert head == before
    assert (repo / "health.txt").read_text(encoding="utf-8").strip() == "1"
