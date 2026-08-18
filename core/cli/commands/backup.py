from __future__ import annotations

import argparse

from core.envfile import load_env
from core.paths import Paths, default_home
from core.services.backup import create_backup, restore_backup


def register(sub: argparse._SubParsersAction) -> None:
    b = sub.add_parser("backup", help="encrypted archive of db, config, work")
    b.set_defaults(handler=run_backup)
    r = sub.add_parser("restore", help="restore a snapshot")
    r.add_argument("snapshot")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(handler=run_restore)


def run_backup(_args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    dest = create_backup(paths)
    print(f"backup: {dest}")
    return 0


def run_restore(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    restore_backup(paths, args.snapshot, dry_run=args.dry_run)
    print("ok" if not args.dry_run else "dry-run ok")
    return 0
