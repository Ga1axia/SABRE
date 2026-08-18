"""Env file owned by the gate user. Secrets never land in config/*.yaml."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from core.paths import Paths, default_home

KNOWN = [
    "SABRE_HOME",
    "SABRE_TOPOLOGY",
    "SABRE_GATE_URL",
    "SABRE_DB_URL",
    "SABRE_SLACK_BOT_TOKEN",
    "SABRE_SLACK_APP_TOKEN",
    "SABRE_OPERATOR_ID",
    "SABRE_INFERENCE_KEY",
    "SABRE_INFERENCE_BASE_URL",
    "SABRE_MIRROR_URL",
    "SABRE_MIRROR_TOKEN",
    "SABRE_KILL_FILE",
    "SABRE_DEV",
]


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_env(paths: Paths | None = None) -> dict[str, str]:
    paths = paths or Paths(default_home())
    data = parse_env_file(paths.env_file)
    for k, v in data.items():
        os.environ.setdefault(k, v)
    return data


def set_env_values(paths: Paths, updates: dict[str, str]) -> None:
    current = parse_env_file(paths.env_file)
    current.update({k: v for k, v in updates.items() if v is not None})
    lines = [f"{k}={current[k]}" for k in sorted(current)]
    paths.env_file.parent.mkdir(parents=True, exist_ok=True)
    paths.env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        paths.env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    for k, v in updates.items():
        os.environ[k] = v
