from __future__ import annotations

import argparse
import time
from pathlib import Path

from core.envfile import load_env
from core.paths import Paths, default_home


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("logs", help="read service logs")
    p.add_argument("--follow", action="store_true")
    p.add_argument("--venture", default=None)
    p.add_argument("--service", default=None)
    p.set_defaults(handler=run)


def _iter_files(logdir: Path, service: str | None) -> list[Path]:
    if service:
        p = logdir / f"{service}.jsonl"
        return [p] if p.exists() else []
    return sorted(logdir.glob("*.jsonl"))


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    files = _iter_files(paths.logs, args.service)
    if not files:
        print("no logs yet")
        return 0

    def dump(path: Path, start: int = 0) -> int:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = text.splitlines()
        for line in lines[start:]:
            if args.venture and args.venture not in line:
                continue
            print(line)
        return len(lines)

    offsets = {p: dump(p) for p in files}
    if not args.follow:
        return 0
    try:
        while True:
            time.sleep(0.5)
            for p in files:
                offsets[p] = dump(p, offsets[p])
    except KeyboardInterrupt:
        return 0
