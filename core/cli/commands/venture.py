from __future__ import annotations

import argparse

from core.db import connect
from core.envfile import load_env
from core.paths import Paths, default_home


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("venture", help="venture list/show/kill")
    sp = p.add_subparsers(dest="action")
    sp.add_parser("list")
    show = sp.add_parser("show")
    show.add_argument("slug")
    kill = sp.add_parser("kill")
    kill.add_argument("slug")
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    if not paths.db.exists():
        print("database not initialized (sabre setup)")
        return 1
    conn = connect(paths.db)
    try:
        action = args.action or "list"
        if action == "list":
            rows = conn.execute(
                "SELECT slug, name, status, created_at FROM ventures ORDER BY created_at"
            ).fetchall()
            if not rows:
                print("no ventures")
                return 0
            for r in rows:
                print(f"{r['slug']:24} {r['status']:12} {r['name']}")
            return 0
        if action == "show":
            r = conn.execute("SELECT * FROM ventures WHERE slug=?", (args.slug,)).fetchone()
            if not r:
                print(f"unknown venture {args.slug}")
                return 1
            for k in r.keys():
                print(f"{k}: {r[k]}")
            return 0
        if action == "kill":
            cur = conn.execute(
                "UPDATE ventures SET status='killed', close_reason='operator', closed_at=datetime('now') WHERE slug=?",
                (args.slug,),
            )
            conn.commit()
            if cur.rowcount == 0:
                print(f"unknown venture {args.slug}")
                return 1
            print(f"killed {args.slug}")
            return 0
    finally:
        conn.close()
    return 0
