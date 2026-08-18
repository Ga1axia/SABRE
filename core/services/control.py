"""Process supervisor used by sabre up. launchd/systemd when installed; pidfiles otherwise."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from core.config import Settings
from core.paths import repo_root

SERVICES = [
    "sabre-gate",
    "sabre-proxy",
    "sabre-hooks",
    "sabre-web",
    "sabre-agent",
    "sabre-push",
    "sabre-watch",
]

MODULES = {
    "sabre-gate": "core.gate.server",
    "sabre-proxy": "core.proxy.server",
    "sabre-hooks": "core.hooks.server",
    "sabre-web": "core.web.console",
    "sabre-agent": "core.runtime.agent",
    "sabre-push": "core.push.publish",
    "sabre-watch": "core.watch.__main__",
}


def _pid_dir(settings: Settings) -> Path:
    d = settings.paths.runtime / "pids"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_file(settings: Settings, name: str) -> Path:
    return _pid_dir(settings) / f"{name}.pid"


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except AttributeError:
        return False


def is_up(settings: Settings, name: str) -> bool:
    pf = _pid_file(settings, name)
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return False
    return _running(pid)


def start_service(settings: Settings, name: str) -> None:
    if is_up(settings, name):
        print(f"  ✓ {name} (already up)")
        return
    mod = MODULES[name]
    log = settings.paths.logs / f"{name}.stdout.log"
    settings.paths.logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SABRE_HOME"] = str(settings.paths.home)
    proc = subprocess.Popen(
        [sys.executable, "-m", mod],
        stdout=log.open("a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(repo_root()),
        start_new_session=True,
    )
    _pid_file(settings, name).write_text(str(proc.pid), encoding="utf-8")
    print(f"  ✓ {name}")


def stop_service(settings: Settings, name: str) -> None:
    pf = _pid_file(settings, name)
    if not pf.exists():
        return
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        pf.unlink(missing_ok=True)
        return
    if _running(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if not _running(pid):
                break
            time.sleep(0.1)
        if _running(pid) and hasattr(signal, "SIGKILL"):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    pf.unlink(missing_ok=True)
    print(f"  ✓ {name} stopped")


def start_all(settings: Settings) -> None:
    if not settings.paths.db.exists():
        from core.db import init_schema

        init_schema(settings.paths.db)
    for name in SERVICES:
        start_service(settings, name)
        time.sleep(0.2)


def stop_all(settings: Settings) -> None:
    for name in reversed(SERVICES):
        stop_service(settings, name)


def restart_service(settings: Settings, name: str) -> None:
    start_service(settings, name)


def status_lines(settings: Settings) -> list[str]:
    lines = []
    for name in SERVICES:
        lines.append(f"{name:16} {'up' if is_up(settings, name) else 'down'}")
    return lines
