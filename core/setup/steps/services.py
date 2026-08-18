from __future__ import annotations

from typing import Any

from core.paths import core_dir

number = 16
name = "Services"
optional = False


def prompt(_ctx: dict[str, Any]) -> dict[str, Any]:
    return {}


def apply(ctx: dict[str, Any], _answers: dict[str, Any]) -> None:
    dest = ctx["paths"].home / "services"
    dest.mkdir(parents=True, exist_ok=True)
    src = core_dir() / "services"
    for tmpl in src.glob("*.tmpl"):
        text = tmpl.read_text(encoding="utf-8")
        text = text.replace("{{SABRE_HOME}}", str(ctx["paths"].home))
        text = text.replace("{{PYTHON}}", "python3")
        (dest / tmpl.name.replace(".tmpl", "")).write_text(text, encoding="utf-8")
    from core.config import load_settings
    from core.runtime.hermes import write_hermes_layout

    write_hermes_layout(ctx["paths"], load_settings(ctx["paths"]))


def verify(ctx: dict[str, Any]) -> str | None:
    dest = ctx["paths"].home / "services"
    if not dest.exists():
        return "service units not rendered"
    return None
