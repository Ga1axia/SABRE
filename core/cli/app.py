"""sabre command dispatcher."""

from __future__ import annotations

import argparse

from core import __version__
from core.cli.commands import (
    accounts,
    backup,
    chat,
    doctor,
    envelope,
    killcmd,
    logs,
    personas,
    secrets,
    services,
    setup,
    status,
    upgrade,
    venture,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sabre", description="SABRE operator CLI")
    parser.add_argument("--version", action="version", version=f"sabre {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    setup.register(sub)
    doctor.register(sub)
    chat.register(sub)
    services.register(sub)
    status.register(sub)
    killcmd.register(sub)
    logs.register(sub)
    envelope.register(sub)
    accounts.register(sub)
    secrets.register(sub)
    venture.register(sub)
    personas.register(sub)
    backup.register(sub)
    upgrade.register(sub)
    return parser
