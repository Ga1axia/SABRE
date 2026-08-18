"""Pre-approved Hermes terminal commands for unattended operation.

Hermes gateway sets HERMES_EXEC_ASK=1, so any local shell command outside this
list waits for human consent and stalls unattended runs. SABRE writes these
patterns to config.yaml ``command_allowlist`` — not YOLO, not session-wide
auto-approve, not smart mode.

Patterns are exact strings or fnmatch globs (no shell operators: no &&, |, ;).
Compound commands never match and fall through to denial.

Anything outside this list is denied by Hermes, reported via tap + alert, and
the agent turn continues (non-blocking hook).
"""

from __future__ import annotations

from pathlib import Path

# Human-readable registry for operators and Stage E acceptance.
ALLOWLIST_REGISTRY: tuple[tuple[str, str], ...] = (
    ("ls", "List directory contents under the venture work tree."),
    ("ls *", "List a specific path without shell metacharacters beyond glob."),
    ("cat *", "Read a file the agent already created or was asked to inspect."),
    ("head *", "Preview the start of a log or source file."),
    ("tail *", "Preview the end of a log or source file."),
    ("pwd", "Confirm cwd stayed inside SABRE work — not an operator path."),
    ("find *", "Locate files while building or debugging a venture."),
    ("wc *", "Count lines/words in artifacts and logs."),
    ("file *", "Identify file types before acting on outputs."),
    ("stat *", "Read metadata (size, mtime) without mutating files."),
    ("grep *", "Search file contents in-repo."),
    ("rg *", "Fast content search when ripgrep is available."),
    ("mkdir *", "Create directories under the company work tree."),
    ("cp *", "Copy artifacts within the work tree."),
    ("mv *", "Rename or move artifacts within the work tree."),
    ("touch *", "Create empty marker files in work."),
    ("git status", "Read working-tree state before a venture commit."),
    ("git diff *", "Inspect unstaged/staged diffs — read-only git."),
    ("git log *", "Inspect history — read-only git."),
    ("git show *", "Inspect a commit — read-only git."),
    ("git add *", "Stage venture-repo changes (publish still goes through gate)."),
    ("git commit *", "Commit staged venture work locally."),
    ("pytest *", "Run automated tests for a venture."),
    ("pip *", "Install Python deps into the venture/venv context."),
    ("uv *", "uv package operations for ventures (matches install.sh toolchain)."),
    ("npm *", "Node build/test for ventures that use npm."),
)


def allowlist_patterns(*, python: str, workdir: str | Path) -> list[str]:
    """Return Hermes command_allowlist entries for this host."""
    py = python
    work = str(workdir)
    patterns = [entry for entry, _why in ALLOWLIST_REGISTRY]
    patterns.extend(
        [
            py,
            f"{py} *",
            "python *",
            "python3 *",
            f"cd {work}",
            f"cd {work} && ls",
        ]
    )
    # cd work && ls is compound — Hermes allowlist rejects compounds. Drop those.
    patterns = [p for p in patterns if "&&" not in p and "|" not in p and ";" not in p]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
