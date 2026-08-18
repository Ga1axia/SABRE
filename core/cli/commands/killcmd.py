from __future__ import annotations

import argparse

from core.config import load_settings
from core.envfile import load_env
from core.paths import Paths, default_home
from core.watch.client import request_kill, request_unkill
from core.watch.killswitch import is_killed


def register(sub: argparse._SubParsersAction) -> None:
    k = sub.add_parser("kill", help="engage kill switch (via watcher)")
    k.set_defaults(handler=run_kill)
    u = sub.add_parser("unkill", help="release kill switch (operator via watcher)")
    u.set_defaults(handler=run_unkill)


def run_kill(_args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    request_kill(settings)
    print(f"kill requested; watcher will engage {paths.kill_file}")
    return 0


def run_unkill(_args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    if not is_killed(paths):
        print("kill switch already clear")
        return 0
    request_unkill(settings)
    print("unkill requested via watcher")
    return 0
