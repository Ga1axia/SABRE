from __future__ import annotations

from typing import Any

from core.config import write_yaml
from core.setup.prompt import ask, os_noninteractive

number = 1
name = "Topology"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"topology": "solo"}
    raw = ask("solo or split", "solo")
    topology = "split" if raw.lower().startswith("s") and raw.lower() != "solo" else "solo"
    if raw.lower() == "split":
        topology = "split"
    host = ""
    if topology == "split":
        host = ask("VPS host (https://gate.example.com)", "")
    return {"topology": topology, "gate_host": host}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    paths = ctx["paths"]
    data = {"topology": answers.get("topology") or "solo"}
    if answers.get("gate_host"):
        data["gate_url"] = answers["gate_host"]
    existing: dict = {}
    if paths.sabre_yaml.exists():
        import yaml

        existing = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
    existing.update(data)
    write_yaml(paths.sabre_yaml, existing)


def verify(ctx: dict[str, Any]) -> str | None:
    paths = ctx["paths"]
    if not paths.sabre_yaml.exists():
        return "sabre.yaml not written"
    return None
