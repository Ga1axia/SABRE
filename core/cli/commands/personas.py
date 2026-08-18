from __future__ import annotations

import argparse

import yaml

from core.envfile import load_env
from core.paths import Paths, default_home
from core.runtime.personas.convert import bundled_personas, convert_all


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("personas", help="persona catalog")
    sp = p.add_subparsers(dest="action")
    sp.add_parser("list")
    sp.add_parser("sync")
    en = sp.add_parser("enable")
    en.add_argument("id")
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    action = args.action or "list"
    catalog = bundled_personas()
    enabled: list[str] = []
    if paths.personas_yaml.exists():
        data = yaml.safe_load(paths.personas_yaml.read_text(encoding="utf-8")) or {}
        enabled = list(data.get("enabled") or [])
    if action == "list":
        for p in catalog:
            mark = "*" if p["id"] in enabled else " "
            print(f"{mark} {p['id']:28} {p['name']}")
        return 0
    if action == "enable":
        if args.id not in {p["id"] for p in catalog}:
            print(f"unknown persona {args.id}")
            return 1
        if args.id not in enabled:
            enabled.append(args.id)
        paths.personas_yaml.parent.mkdir(parents=True, exist_ok=True)
        paths.personas_yaml.write_text(
            yaml.safe_dump({"enabled": enabled}, sort_keys=False), encoding="utf-8"
        )
        convert_all(paths, enabled)
        print(f"enabled {args.id}")
        return 0
    if action == "sync":
        convert_all(paths, enabled or [p["id"] for p in catalog])
        print(f"synced {len(enabled or catalog)} personas")
        return 0
    return 0
