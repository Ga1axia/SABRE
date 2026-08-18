from __future__ import annotations

import argparse

import yaml

from core.envfile import load_env
from core.paths import Paths, default_home


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("accounts", help="account registry (names only)")
    sp = p.add_subparsers(dest="action")
    sp.add_parser("list")
    add = sp.add_parser("add")
    add.add_argument("id")
    add.add_argument("--platform", required=True)
    add.add_argument("--handle", default="")
    add.add_argument("--owner", default="sabre")
    add.add_argument("--credential", required=True, help="proxy://name or env://NAME")
    retire = sp.add_parser("retire")
    retire.add_argument("id")
    p.set_defaults(handler=run)


def _load(paths: Paths) -> dict:
    if not paths.accounts_yaml.exists():
        return {"accounts": [], "denied_hosts": []}
    return yaml.safe_load(paths.accounts_yaml.read_text(encoding="utf-8")) or {
        "accounts": [],
        "denied_hosts": [],
    }


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    data = _load(paths)
    accounts = list(data.get("accounts") or [])
    action = args.action or "list"
    if action == "list":
        if not accounts:
            print("no accounts registered")
            return 0
        for a in accounts:
            print(f"{a.get('id'):20} {a.get('platform'):16} {a.get('status', 'active'):12} {a.get('handle', '')}")
        return 0
    if action == "add":
        accounts = [a for a in accounts if a.get("id") != args.id]
        accounts.append(
            {
                "id": args.id,
                "platform": args.platform,
                "handle": args.handle,
                "owner": args.owner,
                "credential": args.credential,
                "status": "active",
            }
        )
        data["accounts"] = accounts
        paths.accounts_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        print(f"added {args.id} (credential name only)")
        return 0
    if action == "retire":
        found = False
        for a in accounts:
            if a.get("id") == args.id:
                a["status"] = "retired"
                found = True
        if not found:
            print(f"unknown account {args.id}")
            return 1
        data["accounts"] = accounts
        paths.accounts_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        print(f"retired {args.id}")
        return 0
    return 0
