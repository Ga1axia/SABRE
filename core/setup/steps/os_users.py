from __future__ import annotations

import os
import subprocess
from typing import Any

from core.config import is_dev, load_settings
from core.setup.prompt import confirm, os_noninteractive

number = 2
name = "OS users"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if is_dev() or os_noninteractive():
        return {"skip_users": True}
    ok = confirm("Create OS users sabre and sabre-gate? (requires sudo)", True)
    return {"skip_users": not ok}


def _user_exists(name: str) -> bool:
    if os.name == "nt":
        return False
    import pwd

    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    from core.setup.checks import ensure_operator_probe

    ensure_operator_probe()
    if answers.get("skip_users") or is_dev() or os.name == "nt":
        return
    agent = "sabre"
    gate = "sabre-gate"
    for user in (agent, gate):
        if _user_exists(user):
            continue
        if os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
            subprocess.run(["sudo", "sysadminctl", "-addUser", user], check=False)
        else:
            subprocess.run(["sudo", "useradd", "--create-home", "--system", user], check=False)
    home = str(ctx["paths"].home)
    subprocess.run(["sudo", "mkdir", "-p", home], check=False)
    subprocess.run(["sudo", "chown", "-R", f"{gate}:{gate}", str(ctx["paths"].db.parent)], check=False)


def verify(ctx: dict[str, Any]) -> str | None:
    """Users existing is not a pass. Isolation must be proved, or the step is skipped in dest."""
    from core.setup.checks import check_iso_home

    if is_dev() or os.name == "nt":
        return None
    if not _user_exists("sabre") or not _user_exists("sabre-gate"):
        return "users sabre and sabre-gate missing; re-run with sudo or SABRE_DEV=1 for contributor mode"
    settings = ctx.get("settings") or load_settings(ctx["paths"])
    ok, msg = check_iso_home(ctx["paths"], settings)
    if not ok:
        return msg
    return None
