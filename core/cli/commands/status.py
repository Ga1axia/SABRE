from __future__ import annotations

import argparse

from core.config import load_settings
from core.db import connect, current_migration, migration_head
from core.envfile import load_env
from core.paths import Paths, default_home
from core.services.control import status_lines
from core.watch.killswitch import is_killed


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("status", help="one-screen summary")
    p.set_defaults(handler=run)


def run(_args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    print(f"topology: {settings.topology}  posture: {settings.posture}")
    print(f"no-spend: {settings.no_spend}")
    print(f"kill: {'ENGAGED' if is_killed(paths) else 'clear'}")
    print(f"schema: {current_migration(paths.db) or 'missing'} (head {migration_head()})")
    if paths.db.exists():
        conn = connect(paths.db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM ventures WHERE status NOT IN ('killed')").fetchone()[0]
            print(f"ventures: {n}")
        finally:
            conn.close()
    print("services:")
    for line in status_lines(settings):
        print(f"  {line}")
    return 0
