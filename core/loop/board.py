"""File-backed task board. Files under work/board/ are authoritative."""

from __future__ import annotations

from typing import Any

import yaml

from core.ids import new_id
from core.paths import Paths

PRIORITY = {"high": 3, "medium": 2, "low": 1}


def lint_delegation(task: dict[str, Any]) -> list[str]:
    """Reject delegations that lack a goal or acceptance criteria."""
    errors: list[str] = []
    if not str(task.get("goal") or "").strip():
        errors.append("goal required")
    if not str(task.get("acceptance") or "").strip():
        errors.append("acceptance criteria required")
    return errors


def board_dir(paths: Paths):
    dest = paths.work / "board"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def parse_task(text: str) -> dict[str, Any]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        raise ValueError("task file missing YAML frontmatter")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError("task file frontmatter not closed")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError("task frontmatter must be a mapping")
    meta["body"] = parts[2].strip()
    return meta


def render_task(task: dict[str, Any]) -> str:
    body = str(task.get("body") or "")
    fm = {k: v for k, v in task.items() if k != "body" and v is not None}
    return "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + (body + "\n" if body else "")


def write_task(paths: Paths, task: dict[str, Any]) -> dict[str, Any]:
    errors = lint_delegation(task)
    if errors:
        raise ValueError("; ".join(errors))
    task = dict(task)
    task.setdefault("id", new_id("T"))
    task.setdefault("status", "ready")
    task.setdefault("priority", "medium")
    dest = board_dir(paths) / f"{task['id']}.md"
    dest.write_text(render_task(task), encoding="utf-8")
    return task


def list_tasks(paths: Paths) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(board_dir(paths).glob("*.md")):
        try:
            task = parse_task(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError):
            continue
        task.setdefault("id", path.stem)
        out.append(task)
    return out


def load_task(paths: Paths, task_id: str) -> dict[str, Any] | None:
    path = board_dir(paths) / f"{task_id}.md"
    if not path.exists():
        return None
    try:
        task = parse_task(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return None
    task.setdefault("id", task_id)
    return task


def priority_value(task: dict[str, Any]) -> int:
    return PRIORITY.get(str(task.get("priority") or "medium").lower(), 2)


def pick_ready(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    ready = [t for t in tasks if str(t.get("status") or "ready") == "ready"]
    ready.sort(key=lambda t: (-priority_value(t), str(t.get("opened") or t.get("created_at") or "")))
    return ready[0] if ready else None
