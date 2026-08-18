"""PRD §12.5 self-modification: merge, health gate, auto rollback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from core.release.git_ops import merge_with_health_rollback


def apply_core_branch(
    repo: Path,
    branch: str,
    health_check: Callable[[], bool],
) -> tuple[str, str]:
    """Merge branch; roll back to pre-merge HEAD if health_check fails."""
    return merge_with_health_rollback(repo, branch, health_check)
