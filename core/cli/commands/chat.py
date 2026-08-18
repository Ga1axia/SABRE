from __future__ import annotations

import argparse
import subprocess
import sys

from core.config import load_settings
from core.envfile import load_env
from core.paths import Paths, default_home
from core.runtime.agent import preflight
from core.runtime.hermes import hermes_process_env, resolve_hermes_bin, write_hermes_layout


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("chat", help="one-shot Hermes terminal session")
    p.add_argument("-q", "--query", required=True, help="prompt for hermes chat -q")
    p.add_argument("--max-turns", type=int, default=8)
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    write_hermes_layout(paths, settings)
    reason = preflight(paths)
    if reason:
        print(reason, file=sys.stderr)
        return 1
    bin_path = resolve_hermes_bin()
    assert bin_path is not None
    env = hermes_process_env(paths)
    cmd = [bin_path, "chat", "-q", args.query, "--max-turns", str(args.max_turns)]
    return subprocess.call(cmd, env=env, cwd=str(paths.work))
