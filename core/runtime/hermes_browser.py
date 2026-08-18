"""Hermes browser.cdp_url ownership. Unset is safe; anything else must be SABRE-stamped."""

from __future__ import annotations

import os

import yaml

from core.paths import Paths
from core.runtime.hermes import hermes_home


def cdp_marker_path(paths: Paths):
    return hermes_home(paths) / "chrome-debug" / "sabre-cdp-url"


def configured_cdp_url(paths: Paths) -> str:
    env = os.environ.get("BROWSER_CDP_URL", "").strip()
    if env:
        return env
    cfg_path = hermes_home(paths) / "config.yaml"
    if not cfg_path.exists():
        return ""
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    browser = data.get("browser") or {}
    if not isinstance(browser, dict):
        return ""
    return str(browser.get("cdp_url") or "").strip()


def is_sabre_owned_cdp(paths: Paths, url: str) -> bool:
    token = (url or "").strip()
    if not token:
        return True
    marker = cdp_marker_path(paths)
    if not marker.is_file():
        return False
    try:
        owned = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(owned) and owned == token
