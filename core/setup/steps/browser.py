from __future__ import annotations

from typing import Any

from core.runtime.browser import cookie_count, provision, validate_plan

number = 13
name = "Browser profile"
optional = False


def prompt(_ctx: dict[str, Any]) -> dict[str, Any]:
    return {}


def apply(ctx: dict[str, Any], _answers: dict[str, Any]) -> None:
    provision(ctx["paths"])


def verify(ctx: dict[str, Any]) -> str | None:
    paths = ctx["paths"]
    err = validate_plan(paths)
    if err:
        return err
    try:
        n = cookie_count(paths.browser_profile)
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    if n != 0:
        return "cookie jar is not empty"
    return None
