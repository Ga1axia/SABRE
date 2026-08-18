from __future__ import annotations

import argparse

from core.config import load_settings, write_yaml
from core.envfile import load_env
from core.paths import Paths, default_home


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("envelope", help="show or set envelope keys")
    sp = p.add_subparsers(dest="action")
    sp.add_parser("show")
    s = sp.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    p.set_defaults(handler=run)


def _set_path(data: dict, dotted: str, value: str) -> None:
    parts = dotted.split(".")
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    raw: object = value
    try:
        if "." in value:
            raw = float(value)
        else:
            raw = int(value)
    except ValueError:
        raw = value
    cur[parts[-1]] = raw


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    envelopes = dict(settings.envelopes)
    if args.action == "set":
        _set_path(envelopes, args.key, args.value)
        write_yaml(paths.envelopes_yaml, {"envelopes": envelopes})
        print(f"set envelopes.{args.key} = {args.value}")
        print("envelope changes are Red for the agent; this CLI write is operator-only.")
        return 0
    import yaml

    print(yaml.safe_dump({"envelopes": envelopes}, sort_keys=False))
    return 0
