"""Git rollback for self-modification merges and upgrade restore."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=False)


def current_head(repo: Path) -> str:
    r = _run(["git", "-C", str(repo), "rev-parse", "HEAD"], cwd=repo)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git rev-parse failed")
    return r.stdout.strip()


def prior_rollback_ref(repo: Path) -> str:
    """Nearest annotated tag at HEAD, else HEAD itself."""
    r = _run(["git", "-C", str(repo), "describe", "--tags", "--abbrev=0"], cwd=repo)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return current_head(repo)


def checkout_ref(repo: Path, ref: str) -> None:
    r = _run(["git", "-C", str(repo), "checkout", "--force", ref], cwd=repo)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git checkout {ref} failed")


def merge_with_health_rollback(
    repo: Path,
    branch: str,
    health_check: Callable[[], bool],
) -> tuple[str, str]:
    """Merge branch into current HEAD. Roll back on failed health_check.

    Returns (outcome, head) where outcome is 'merged' or 'rolled_back'.
    """
    before = current_head(repo)
    r = _run(["git", "-C", str(repo), "merge", "--no-edit", branch], cwd=repo)
    if r.returncode != 0:
        _run(["git", "-C", str(repo), "merge", "--abort"], cwd=repo)
        raise RuntimeError(r.stderr.strip() or f"git merge {branch} failed")
    if health_check():
        return "merged", current_head(repo)
    _run(["git", "-C", str(repo), "reset", "--hard", before], cwd=repo)
    return "rolled_back", current_head(repo)
