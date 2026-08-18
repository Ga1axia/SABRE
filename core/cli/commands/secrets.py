from __future__ import annotations

import argparse

from core.envfile import load_env
from core.paths import Paths, default_home
from core.proxy.store import add_secret, list_secrets, rotate_secret


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("secrets", help="credential names only; never values")
    sp = p.add_subparsers(dest="action")
    sp.add_parser("list")
    add = sp.add_parser("add")
    add.add_argument("name")
    add.add_argument("--tier", type=int, choices=[1, 2], default=2)
    add.add_argument("--value", default=None, help="read from prompt if omitted")
    rot = sp.add_parser("rotate")
    rot.add_argument("name")
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    action = args.action or "list"
    if action == "list":
        rows = list_secrets(paths)
        if not rows:
            print("no secrets")
            return 0
        for r in rows:
            print(f"{r['name']:24} tier={r['tier']} uses={r['uses']} last={r['last_used'] or '-'}")
        return 0
    if action == "add":
        value = args.value
        if not value:
            import getpass

            value = getpass.getpass(f"value for {args.name} (never echoed): ")
        add_secret(paths, args.name, value, tier=args.tier)
        print(f"stored {args.name} (value not shown)")
        return 0
    if action == "rotate":
        import getpass

        value = getpass.getpass(f"new value for {args.name}: ")
        rotate_secret(paths, args.name, value)
        print(f"rotated {args.name}")
        return 0
    return 0
