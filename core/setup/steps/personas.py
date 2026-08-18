from __future__ import annotations

from typing import Any

from core.config import write_yaml
from core.runtime.personas.convert import bundled_personas, convert_all
from core.setup.prompt import os_noninteractive

number = 14
name = "Personas"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    ids = [p["id"] for p in bundled_personas()]
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"enabled": ids}
    print(f"       Bundled: {', '.join(ids)}")
    return {"enabled": ids}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    enabled = answers.get("enabled") or [p["id"] for p in bundled_personas()]
    write_yaml(ctx["paths"].personas_yaml, {"enabled": enabled})
    n = convert_all(ctx["paths"], enabled)
    answers["_count"] = n


def verify(ctx: dict[str, Any]) -> str | None:
    dest = ctx["paths"].home / "personas"
    if not dest.exists() or not list(dest.glob("*.md")):
        # also accept repo core/runtime/personas
        from core.paths import core_dir

        if not list((core_dir() / "runtime" / "personas").glob("*.md")):
            return "no converted personas"
    return None
