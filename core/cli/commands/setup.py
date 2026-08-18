from __future__ import annotations

import argparse

from core.envfile import load_env
from core.paths import Paths, default_home
from core.setup.wizard import run_wizard


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("setup", help="interactive wizard")
    p.add_argument("--step", type=int, default=None)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--non-interactive", action="store_true")
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    paths.ensure()
    load_env(paths)
    return run_wizard(paths, step=args.step, resume=args.resume, interactive=not args.non_interactive)
