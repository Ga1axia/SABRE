from __future__ import annotations

import os
from typing import Any

from core.config import write_yaml
from core.envfile import set_env_values
from core.setup.prompt import ask, os_noninteractive

number = 7
name = "Operator identity"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    default = os.environ.get("SABRE_OPERATOR_ID") or ""
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"operator_id": default}
    oid = ask("Your Slack member ID (U…)", default)
    return {"operator_id": oid}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    oid = answers.get("operator_id") or ""
    if oid:
        set_env_values(ctx["paths"], {"SABRE_OPERATOR_ID": oid})
        import yaml

        cfg = {}
        if ctx["paths"].sabre_yaml.exists():
            cfg = yaml.safe_load(ctx["paths"].sabre_yaml.read_text(encoding="utf-8")) or {}
        cfg["operator_id"] = oid
        write_yaml(ctx["paths"].sabre_yaml, cfg)


def verify(ctx: dict[str, Any]) -> str | None:
    oid = os.environ.get("SABRE_OPERATOR_ID")
    if not oid:
        return "SABRE_OPERATOR_ID missing"
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return None
    try:
        from core.drivers.messaging.slack import SlackDriver

        user = SlackDriver().lookup_user(oid)
        if not user.get("id"):
            return f"Slack user {oid} did not resolve"
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return None
