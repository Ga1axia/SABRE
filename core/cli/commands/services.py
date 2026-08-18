from __future__ import annotations

import argparse

from core.config import load_settings
from core.envfile import load_env
from core.paths import Paths, default_home
from core.services.control import restart_service, start_all, stop_all, stop_service


def register(sub: argparse._SubParsersAction) -> None:
    up = sub.add_parser("up", help="start all services")
    up.add_argument("--dev", action="store_true")
    up.set_defaults(handler=run_up)

    down = sub.add_parser("down", help="stop all services")
    down.set_defaults(handler=run_down)

    restart = sub.add_parser("restart", help="restart one or all services")
    restart.add_argument("service", nargs="?", default=None)
    restart.set_defaults(handler=run_restart)


def run_up(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    from core.setup.doctor import run_doctor

    report = run_doctor(paths, fix=False)
    waive = bool(args.dev)
    blocking = report.blocking_fatals(waive_isolation=waive)
    if blocking:
        print(report.format())
        print("sabre up refused. Isolation cannot be waived except with --dev; other fatals always block.")
        return 1
    if waive and any(
        r.severity == "fatal" and not r.ok and r.id.startswith("isolation.") for r in report.results
    ):
        print("warning: --dev waived isolation.* only. You have no OS-user security properties.")
    start_all(settings)
    host, port = settings.console_bind
    print(f"  Console: http://{host}:{port}")
    print("  Slack:   #directives")
    return 0


def run_down(_args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    stop_all(load_settings(paths))
    return 0


def run_restart(args: argparse.Namespace) -> int:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    if args.service:
        stop_service(settings, args.service)
        restart_service(settings, args.service)
    else:
        stop_all(settings)
        start_all(settings)
    return 0
