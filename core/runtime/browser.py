"""Dedicated Chromium profile. Always launched with an explicit isolated user-data-dir."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.errors import SabreError
from core.paths import Paths

PLAN_NAME = "browser-launch.json"
USER_DATA_FLAG = "--user-data-dir"

_BINARIES = (
    os.environ.get("SABRE_BROWSER_BIN") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
    shutil.which("google-chrome") or "",
    shutil.which("google-chrome-stable") or "",
    shutil.which("msedge") or "",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def profile_dir(paths: Paths) -> Path:
    return paths.browser_profile.resolve()


def resolve_binary() -> str | None:
    override = os.environ.get("SABRE_BROWSER_BIN")
    if override:
        p = Path(override)
        if p.exists():
            return str(p)
        found = shutil.which(override)
        if found:
            return found
    for candidate in _BINARIES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def launch_argv(paths: Paths, binary: str | None = None) -> list[str]:
    exe = binary or resolve_binary()
    if not exe:
        raise SabreError("no chromium-family browser", remedy="install Chrome or Edge, or set SABRE_BROWSER_BIN")
    udd = str(profile_dir(paths))
    return [
        exe,
        f"{USER_DATA_FLAG}={udd}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-sync",
        "--noerrdialogs",
    ]


def user_data_dir_from_argv(argv: list[str] | None) -> Path | None:
    args = list(argv or [])
    for i, item in enumerate(args):
        if item.startswith(f"{USER_DATA_FLAG}="):
            return Path(item.split("=", 1)[1])
        if item == USER_DATA_FLAG and i + 1 < len(args):
            return Path(args[i + 1])
    return None


def plan_path(paths: Paths) -> Path:
    return paths.runtime / PLAN_NAME


def write_launch_plan(paths: Paths, argv: list[str] | None = None) -> dict[str, Any]:
    paths.runtime.mkdir(parents=True, exist_ok=True)
    profile_dir(paths).mkdir(parents=True, exist_ok=True)
    args = list(argv) if argv is not None else launch_argv(paths)
    udd = user_data_dir_from_argv(args)
    plan = {
        "argv": args,
        "user_data_dir": str(udd) if udd else "",
    }
    dest = plan_path(paths)
    dest.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def operator_profiles() -> list[Path]:
    home = Path.home()
    return [
        home / "AppData/Local/Google/Chrome/User Data",
        home / "AppData/Local/Microsoft/Edge/User Data",
        home / "Library/Application Support/Google/Chrome",
        home / "Library/Application Support/Microsoft Edge",
        home / ".config/google-chrome",
        home / ".config/chromium",
    ]


def validate_plan(paths: Paths) -> str | None:
    dest = plan_path(paths)
    if not dest.exists():
        return "browser launch plan missing"
    try:
        plan = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "browser launch plan unreadable"
    argv = plan.get("argv") if isinstance(plan, dict) else None
    if not isinstance(argv, list):
        return "browser launch plan missing argv"
    udd = user_data_dir_from_argv([str(a) for a in argv])
    if udd is None:
        return "launch argv missing --user-data-dir"
    expected = profile_dir(paths)
    try:
        got = udd.expanduser().resolve()
    except OSError:
        return f"user-data-dir unreadable: {udd}"
    if got != expected:
        return f"user-data-dir points at {got}, not {expected}"
    for op in operator_profiles():
        if not op.exists():
            continue
        other = op.resolve()
        if got == other or other in got.parents or got in other.parents:
            return f"user-data-dir overlaps operator profile {other}"
    return None


def cookie_files(profile: Path) -> list[Path]:
    root = Path(profile)
    candidates = [
        root / "Default" / "Network" / "Cookies",
        root / "Default" / "Cookies",
        root / "Cookies",
    ]
    return [p for p in candidates if p.exists() and p.is_file()]


def cookie_count(profile: Path) -> int:
    total = 0
    found = False
    for path in cookie_files(profile):
        found = True
        try:
            uri = path.resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            try:
                total += int(conn.execute("SELECT COUNT(*) FROM cookies").fetchone()[0])
            finally:
                conn.close()
        except sqlite3.Error:
            if path.stat().st_size > 8192:
                raise SabreError(
                    f"cookie jar unreadable at {path}",
                    remedy="delete HERMES_HOME/chrome-debug and re-run setup",
                ) from None
    if not found:
        return 0
    return total


def load_page(paths: Paths, url: str, *, timeout: int = 45) -> dict[str, Any]:
    """Load url in the isolated profile and return dumped document text."""
    argv = launch_argv(paths)
    write_launch_plan(paths, argv)
    run = [*argv, "--dump-dom", "--virtual-time-budget=8000", url]
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "timeout": timeout,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(run, check=False, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise SabreError(f"browser timed out loading {url}", remedy="retry; check display/sandbox") from exc
    content = proc.stdout or ""
    if not content.strip() and proc.stderr:
        content = proc.stderr
    return {
        "url": url,
        "content": content,
        "status": proc.returncode,
        "argv": run,
    }


def provision(paths: Paths) -> dict[str, Any]:
    profile = profile_dir(paths)
    profile.mkdir(parents=True, exist_ok=True)
    readme = profile / "README"
    if not readme.exists():
        readme.write_text(
            "SABRE dedicated browser profile. Never attach the operator's debugging endpoint.\n",
            encoding="utf-8",
        )
    return write_launch_plan(paths)


def main() -> int:
    from core.envfile import load_env
    from core.paths import default_home

    load_env()
    url = sys.argv[1] if len(sys.argv) > 1 else "about:blank"
    result = load_page(Paths(default_home()), url)
    sys.stdout.write(result["content"])
    return 0 if result["content"].strip() else 1


if __name__ == "__main__":
    raise SystemExit(main())
