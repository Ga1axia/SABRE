from __future__ import annotations

from typing import Any

from core.certs import certs_present, generate_mtls

number = 4
name = "Certificates"
optional = False


def prompt(_ctx: dict[str, Any]) -> dict[str, Any]:
    return {}


def apply(ctx: dict[str, Any], _answers: dict[str, Any]) -> None:
    generate_mtls(ctx["paths"])


def verify(ctx: dict[str, Any]) -> str | None:
    if not certs_present(ctx["paths"]):
        return "mTLS certs missing"
    return None
