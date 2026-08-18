"""Operator-owned kill file. Mode 444. Agent cannot create, delete, or modify it."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from core.paths import Paths

MARKER = "SABRE KILL SWITCH ENGAGED\n"


def is_killed(paths: Paths) -> bool:
    return paths.kill_file.exists()


def engage(paths: Paths) -> None:
    paths.kill_file.parent.mkdir(parents=True, exist_ok=True)
    if paths.kill_file.exists():
        try:
            paths.kill_file.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
    paths.kill_file.write_text(MARKER, encoding="utf-8")
    try:
        paths.kill_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass


def release(paths: Paths) -> None:
    if not paths.kill_file.exists():
        return
    try:
        paths.kill_file.chmod(stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    paths.kill_file.unlink()


def install_readonly(paths: Paths, owner: str | None = None) -> None:
    """Create the file as the operator with mode 444. Content empty means NOT killed.
    We use a sibling sentinel .installed so doctor can see the switch exists.
    """
    sentinel = Path(str(paths.kill_file) + ".installed")
    if sentinel.exists():
        try:
            sentinel.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
    sentinel.write_text("installed\n", encoding="utf-8")
    try:
        sentinel.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass
    if owner and os.name != "nt":
        import pwd

        uid = pwd.getpwnam(owner).pw_uid
        gid = pwd.getpwnam(owner).pw_gid
        os.chown(sentinel, uid, gid)


def present(paths: Paths) -> bool:
    return Path(str(paths.kill_file) + ".installed").exists() or paths.kill_file.exists()
