"""Resumable setup wizard. Each step is prompt → apply → verify."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core.config import is_dev, load_defaults
from core.paths import Paths
from core.setup import prompt as pr
from core.setup.steps import STEPS


class Step(Protocol):
    number: int
    name: str
    optional: bool

    def prompt(self, ctx: dict[str, Any]) -> dict[str, Any]: ...
    def apply(self, ctx: dict[str, Any], answers: dict[str, Any]) -> None: ...
    def verify(self, ctx: dict[str, Any]) -> str | None: ...


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"completed": [], "answers": {}, "skipped": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


@dataclass
class Ctx:
    paths: Paths
    defaults: dict[str, Any]
    interactive: bool
    state: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "paths": self.paths,
            "defaults": self.defaults,
            "interactive": self.interactive,
            "state": self.state,
            "dev": is_dev(),
        }


def run_wizard(
    paths: Paths,
    step: int | None = None,
    resume: bool = True,
    interactive: bool = True,
) -> int:
    paths.ensure()
    state = _load_state(paths.setup_state)
    ctx = Ctx(paths, load_defaults(), interactive, state)
    total = len(STEPS)
    selected = list(STEPS)
    if step is not None:
        selected = [s for s in STEPS if s.number == step]
        if not selected:
            print(f"unknown step {step}")
            return 1
        resume = False

    for s in selected:
        if resume and s.number in state.get("completed", []) and step is None:
            continue
        pr.announce(s.number, total, s.name)
        answers = s.prompt(ctx.as_dict()) if interactive else s.prompt({**ctx.as_dict(), "interactive": False})
        if s.optional and answers.get("skip"):
            skipped = set(state.get("skipped") or [])
            skipped.add(s.number)
            state["skipped"] = sorted(skipped)
            if s.number not in state["completed"]:
                state["completed"].append(s.number)
            _save_state(paths.setup_state, state)
            print("       skipped (degraded mode)")
            continue
        s.apply(ctx.as_dict(), answers)
        err = s.verify(ctx.as_dict())
        if err:
            print(f"       ✗ {err}")
            _save_state(paths.setup_state, state)
            return 1
        if s.number not in state["completed"]:
            state["completed"].append(s.number)
        state.setdefault("answers", {})[str(s.number)] = {
            k: v
            for k, v in answers.items()
            if k not in {"key", "token", "bot_token", "app_token", "value"}
        }
        _save_state(paths.setup_state, state)
        print("       ✓")
    print("Setup complete. Run: sabre doctor")
    return 0
