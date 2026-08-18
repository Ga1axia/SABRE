from __future__ import annotations

from typing import Any

from core.config import write_yaml
from core.setup.prompt import confirm, os_noninteractive

number = 11
name = "Payments"
optional = True


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"skip": True}
    if not confirm("Configure a payment processor now?", False):
        return {"skip": True}
    return {"skip": False}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    import yaml

    cfg = {}
    if ctx["paths"].sabre_yaml.exists():
        cfg = yaml.safe_load(ctx["paths"].sabre_yaml.read_text(encoding="utf-8")) or {}
    cfg.setdefault("drivers", {})["payments"] = {
        "name": "disabled",
        "enabled": not answers.get("skip", True),
    }
    write_yaml(ctx["paths"].sabre_yaml, cfg)


def verify(_ctx: dict[str, Any]) -> str | None:
    return None
