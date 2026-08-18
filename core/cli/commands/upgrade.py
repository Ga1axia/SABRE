from __future__ import annotations

import argparse
import subprocess

from core.config import load_settings
from core.db import apply_migrations, connect, init_schema
from core.envfile import load_env
from core.paths import Paths, default_home, repo_root
from core.services.backup import create_backup, restore_backup
from core.release.git_ops import checkout_ref, prior_rollback_ref
from core.services.control import start_all, stop_all


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("upgrade", help="fetch, migrate, doctor, restart")
    p.add_argument("--to", dest="ref", default=None)
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    snapshot = create_backup(paths)
    print(f"pre-upgrade backup: {snapshot}")
    stop_all(settings)
    app = paths.app if (paths.app / ".git").exists() else repo_root()
    rollback_ref = prior_rollback_ref(app) if (app / ".git").exists() else None
    if rollback_ref:
        print(f"rollback floor: {rollback_ref}")
    if (app / ".git").exists():
        ref = args.ref or "main"
        subprocess.run(["git", "-C", str(app), "fetch"], check=False)
        subprocess.run(["git", "-C", str(app), "checkout", ref], check=False)
        subprocess.run(["git", "-C", str(app), "pull", "--ff-only"], check=False)
    try:
        if paths.db.exists():
            conn = connect(paths.db)
            try:
                apply_migrations(conn)
                conn.commit()
            finally:
                conn.close()
        else:
            init_schema(paths.db)
        from core.setup.doctor import run_doctor

        report = run_doctor(paths)
        print(report.format())
        if not report.ok:
            if rollback_ref and (app / ".git").exists():
                checkout_ref(app, rollback_ref)
                print(f"git rolled back to {rollback_ref}")
            restore_backup(paths, str(snapshot))
            print("restored pre-upgrade snapshot")
            return 1
        start_all(settings)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"upgrade failed: {exc}")
        if rollback_ref and (app / ".git").exists():
            try:
                checkout_ref(app, rollback_ref)
                print(f"git rolled back to {rollback_ref}")
            except Exception as rb_exc:  # noqa: BLE001
                print(f"git rollback failed: {rb_exc}")
        try:
            restore_backup(paths, str(snapshot))
            print("restored pre-upgrade snapshot")
        except Exception as rs_exc:  # noqa: BLE001
            print(f"snapshot restore failed: {rs_exc}")
        return 1
