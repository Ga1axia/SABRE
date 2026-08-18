from __future__ import annotations

from typing import Any

from core.envfile import set_env_values
from core.setup.prompt import confirm, os_noninteractive

number = 15
name = "Mirror"
optional = True


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"skip": True}
    if not confirm("Deploy the hosted read-only mirror now?", False):
        return {"skip": True}
    from core.setup.prompt import ask

    return {"skip": False, "url": ask("Mirror URL", "")}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    if answers.get("skip") or not answers.get("url"):
        return
    set_env_values(ctx["paths"], {"SABRE_MIRROR_URL": answers["url"]})


def verify(_ctx: dict[str, Any]) -> str | None:
    return None
