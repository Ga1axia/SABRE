from __future__ import annotations

import argparse
import json

from core.envfile import load_env
from core.paths import Paths, default_home
from core.setup.doctor import run_doctor


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("doctor", help="preflight verification")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fix", action="store_true")
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    report = run_doctor(paths, fix=args.fix)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.format())
    return 0 if report.ok else 1
