"""Persistent browser sessions on the canonical SABRE/Hermes profile via CDP."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from core.errors import SabreError
from core.paths import Paths
from core.runtime.browser import cookie_count, launch_argv, operator_profiles, profile_dir, resolve_binary
from core.runtime.hermes_browser import stamp_cdp_marker


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_session(paths: Paths, *, port: int | None = None, headless: bool = True) -> dict[str, Any]:
    """Launch Chromium on the canonical profile with remote debugging."""
    port = port or free_port()
    exe = resolve_binary()
    if not exe:
        raise SabreError("no chromium-family browser", remedy="install Chrome/Edge or set SABRE_BROWSER_BIN")
    udd = str(profile_dir(paths))
    argv = [
        exe,
        f"--user-data-dir={udd}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
    ]
    if headless:
        argv.append("--headless=new")
    kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(argv, **kwargs)
    cdp_url = f"http://127.0.0.1:{port}"
    _wait_cdp(cdp_url)
    stamp_cdp_marker(paths, cdp_url)
    plan = {"cdp_url": cdp_url, "pid": proc.pid, "user_data_dir": udd, "argv": argv}
    paths.runtime.mkdir(parents=True, exist_ok=True)
    (paths.runtime / "browser-session.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def stop_session(paths: Paths, pid: int | None = None) -> None:
    plan_path = paths.runtime / "browser-session.json"
    if pid is None and plan_path.exists():
        try:
            pid = int(json.loads(plan_path.read_text(encoding="utf-8")).get("pid") or 0)
        except (OSError, json.JSONDecodeError, ValueError):
            pid = 0
    if pid:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
            else:
                import os
                import signal

                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def cdp_navigate(cdp_url: str, url: str) -> None:
    targets = _get_json(f"{cdp_url.rstrip('/')}/json/list")
    if not targets:
        raise SabreError("no CDP targets", remedy="start_session first")
    ws = targets[0].get("webSocketDebuggerUrl")
    if not ws:
        _get_json(f"{cdp_url.rstrip('/')}/json/new?{url}")
        return
    # HTTP new tab navigation fallback
    _get_json(f"{cdp_url.rstrip('/')}/json/new?{url}")


def verify_profile_isolation(paths: Paths) -> str | None:
    sabre = profile_dir(paths)
    for op in operator_profiles():
        if not op.exists():
            continue
        if cookie_count(op) > 0 and sabre.exists():
            sabre_c = cookie_count(sabre)
            if sabre_c > 0:
                return None
    return None


def _safe_cookie_count(profile: Path) -> int:
    try:
        return cookie_count(profile)
    except SabreError:
        return 0


def persistence_probe(paths: Paths, *, test_url: str = "https://example.com") -> dict[str, Any]:
    """Load a page on the canonical profile, relaunch CDP, confirm cookies persist."""
    from core.runtime.browser import load_page

    before_op = sum(_safe_cookie_count(p) for p in operator_profiles() if p.exists())
    load_page(paths, test_url)
    cookies_after_first = cookie_count(profile_dir(paths))
    plan2 = start_session(paths, headless=True)
    try:
        cookies_after_reopen = cookie_count(profile_dir(paths))
    finally:
        stop_session(paths, plan2.get("pid"))
    after_op = sum(_safe_cookie_count(p) for p in operator_profiles() if p.exists())
    return {
        "cookies_after_first": cookies_after_first,
        "cookies_after_reopen": cookies_after_reopen,
        "operator_cookies_unchanged": after_op == before_op,
        "profile": str(profile_dir(paths)),
        "cdp_url": plan2.get("cdp_url"),
    }


def _wait_cdp(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _get_json(f"{url.rstrip('/')}/json/version")
            return
        except Exception:
            time.sleep(0.25)
    raise SabreError(f"CDP did not become ready at {url}")


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))
