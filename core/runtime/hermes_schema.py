"""Hermes v0.20.1 config schema. Keys SABRE writes must be in this tree."""

from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from typing import Any

from core.paths import core_dir

HERMES_VERSION = "0.20.1"

# Hermes pre_llm_call / on_session_start stdin has no Slack channel field.
# extra.platform is "slack" | "cli" | ...; extra.sender_id is the user id.
HOOK_SLACK_CHANNEL_FIELD = None
HOOK_PLATFORM_FIELD = "extra.platform"
HOOK_SENDER_FIELD = "extra.sender_id"

NOT_IMPLEMENTED = {
    "browser.user_data_dir": (
        "Hermes has no user_data_dir config key. Local CDP Chrome uses the "
        "hardcoded path HERMES_HOME/chrome-debug (hermes_cli.browser_connect)."
    ),
    "browser.headless": "Hermes key is browser.headed (true = visible window).",
    "cron.jobs-in-config": (
        "Hermes config cron: is a settings mapping, not a job list. SABRE writes "
        "jobs to HERMES_HOME/cron/jobs.json. A list under config.yaml cron: is a regression."
    ),
    "hook.channel": (
        "Hermes does not put channel, channel_id, or channel_name on hook stdin. "
        "Channel contracts are resolved from HERMES_HOME/state.db sessions.chat_id "
        "by session_id (hermes_state.SessionDB / record_gateway_session_peer)."
    ),
}


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    path = core_dir() / "runtime" / "hermes_v0_20_1_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def unknown_written_keys(cfg: dict[str, Any]) -> list[str]:
    """Dotted paths in cfg that Hermes v0.20.1 does not recognise."""
    schema = load_schema()
    defaults = schema["defaults"]
    extra = set(schema["extra_roots"])
    open_dicts = set(schema["open_dicts"])
    schema_dicts = set(schema["schema_defined_dicts"])
    known_roots = set(defaults) | extra | open_dicts | schema_dicts
    unknown: list[str] = []
    for key, value in cfg.items():
        if str(key).startswith("_") and key != "_config_version":
            continue
        if key not in known_roots:
            unknown.append(str(key))
            continue
        if key in open_dicts or key in schema_dicts:
            continue
        node = defaults.get(key)
        if key == "model":
            unknown.extend(_model_unknowns(value, schema["model_object_keys"]))
            continue
        if isinstance(node, dict):
            if not isinstance(value, dict):
                unknown.append(f"{key} (expected mapping, got {type(value).__name__})")
                continue
            unknown.extend(_walk(value, node, key, open_dicts))
    return unknown


def _model_unknowns(value: Any, object_keys: list[str]) -> list[str]:
    if value is None or isinstance(value, str):
        return []
    if not isinstance(value, dict):
        return [f"model (expected string or mapping, got {type(value).__name__})"]
    allowed = set(object_keys)
    return [f"model.{k}" for k in value if k not in allowed]


def _walk(value: dict[str, Any], node: dict[str, Any], prefix: str, open_dicts: set[str]) -> list[str]:
    unknown: list[str] = []
    for key, child in value.items():
        path = f"{prefix}.{key}"
        if key not in node:
            unknown.append(path)
            continue
        schema_child = node[key]
        if isinstance(schema_child, dict):
            if not isinstance(child, dict):
                unknown.append(f"{path} (expected mapping, got {type(child).__name__})")
                continue
            unknown.extend(_walk(child, schema_child, path, open_dicts))
    return unknown


def installed_hermes_version() -> str | None:
    """Best-effort version string from `hermes --version`. None if unreadable."""
    from core.runtime.hermes import resolve_hermes_bin

    bin_path = resolve_hermes_bin()
    if not bin_path:
        return None
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = f"{result.stdout or ''}\n{result.stderr or ''}"
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", text)
    if match:
        return match.group(1)
    stripped = text.strip()
    return stripped or None
