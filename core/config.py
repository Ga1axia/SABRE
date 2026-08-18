"""Three-layer config: defaults.yaml < config/*.yaml < SABRE_* env."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.paths import Paths, core_dir, default_home


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_defaults() -> dict[str, Any]:
    return _read_yaml(core_dir() / "defaults.yaml")


def is_dev() -> bool:
    return os.environ.get("SABRE_DEV", "").strip() in {"1", "true", "yes"}


@dataclass
class Settings:
    paths: Paths
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def topology(self) -> str:
        return str(self.raw.get("topology") or os.environ.get("SABRE_TOPOLOGY") or "solo")

    @property
    def posture(self) -> str:
        return str(self.raw.get("posture") or "lean")

    @property
    def agent_user(self) -> str:
        users = self.raw.get("users") or {}
        return str(users.get("agent") or "sabre")

    @property
    def gate_user(self) -> str:
        users = self.raw.get("users") or {}
        return str(users.get("gate") or "sabre-gate")

    @property
    def gate_url(self) -> str:
        env = os.environ.get("SABRE_GATE_URL")
        if env:
            return env
        port = int((self.raw.get("paths") or {}).get("gate_port") or 8788)
        return f"https://127.0.0.1:{port}"

    @property
    def console_bind(self) -> tuple[str, int]:
        p = self.raw.get("paths") or {}
        return str(p.get("console_host") or "127.0.0.1"), int(p.get("console_port") or 8787)

    @property
    def watch_url(self) -> str:
        port = int((self.raw.get("paths") or {}).get("watch_port") or 8791)
        return f"http://127.0.0.1:{port}"

    @property
    def no_spend(self) -> bool:
        cards = (self.raw.get("drivers") or {}).get("cards") or {}
        return not bool(cards.get("enabled"))

    @property
    def envelopes(self) -> dict[str, Any]:
        return dict(self.raw.get("envelopes") or {})

    @property
    def channels(self) -> list[str]:
        return list(self.raw.get("channels") or [])

    @property
    def drivers(self) -> dict[str, Any]:
        return dict(self.raw.get("drivers") or {})

    def driver_enabled(self, slot: str) -> bool:
        d = self.drivers.get(slot) or {}
        if "enabled" in d:
            return bool(d["enabled"])
        return slot in {"inference", "messaging"}

    def operator_id(self) -> str:
        return str(os.environ.get("SABRE_OPERATOR_ID") or self.raw.get("operator_id") or "")

    @property
    def task_lease_seconds(self) -> int:
        return int(self.raw.get("task_lease_seconds") or 900)

    @property
    def red_expire_days(self) -> int:
        return int(self.raw.get("red_expire_days") or 7)

    @property
    def delegation(self) -> dict[str, Any]:
        return dict(self.raw.get("delegation") or {})

    @property
    def loop_caps(self) -> dict[str, Any]:
        return dict(self.raw.get("loop_caps") or {})

    @property
    def compression(self) -> dict[str, Any]:
        return dict(self.raw.get("compression") or {})


def load_settings(paths: Paths | None = None) -> Settings:
    paths = paths or Paths(default_home())
    raw = load_defaults()
    for name in ("sabre.yaml", "envelopes.yaml", "accounts.yaml", "personas.yaml"):
        raw = _deep_merge(raw, _read_yaml(paths.config_dir / name))
    return Settings(paths=paths, raw=raw)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
