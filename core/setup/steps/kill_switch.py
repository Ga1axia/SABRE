from __future__ import annotations

import os
from typing import Any

from core.watch.killswitch import install_readonly, present

number = 17
name = "Kill switch"
optional = False


def prompt(_ctx: dict[str, Any]) -> dict[str, Any]:
    return {}


def apply(ctx: dict[str, Any], _answers: dict[str, Any]) -> None:
    owner = os.environ.get("USER") or os.environ.get("USERNAME") or None
    install_readonly(ctx["paths"], owner=None if os.name == "nt" else owner)


def verify(ctx: dict[str, Any]) -> str | None:
    if not present(ctx["paths"]):
        return "kill switch sentinel missing"
    return None
