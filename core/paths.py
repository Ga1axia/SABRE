"""Filesystem layout. Resolved from SABRE_HOME; never hardcoded sockets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def default_home() -> Path:
    raw = os.environ.get("SABRE_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".sabre"


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def app(self) -> Path:
        return self.home / "app"

    @property
    def config_dir(self) -> Path:
        return self.home / "config"

    @property
    def work(self) -> Path:
        return self.home / "work"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def runtime(self) -> Path:
        return self.home / "runtime"

    @property
    def certs(self) -> Path:
        return self.home / "certs"

    @property
    def secrets(self) -> Path:
        return self.home / "secrets"

    @property
    def backups(self) -> Path:
        return self.home / "backups"

    @property
    def db(self) -> Path:
        return self.home / "sabre.db"

    @property
    def env_file(self) -> Path:
        return self.home / "env"

    @property
    def kill_file(self) -> Path:
        override = os.environ.get("SABRE_KILL_FILE")
        if override:
            return Path(override).expanduser()
        return self.home / "KILL"

    @property
    def setup_state(self) -> Path:
        return self.config_dir / "setup.json"

    @property
    def sabre_yaml(self) -> Path:
        return self.config_dir / "sabre.yaml"

    @property
    def envelopes_yaml(self) -> Path:
        return self.config_dir / "envelopes.yaml"

    @property
    def accounts_yaml(self) -> Path:
        return self.config_dir / "accounts.yaml"

    @property
    def personas_yaml(self) -> Path:
        return self.config_dir / "personas.yaml"

    @property
    def browser_profile(self) -> Path:
        return self.home / "hermes" / "chrome-debug"

    @property
    def proxy_store(self) -> Path:
        return self.secrets / "proxy.json"

    @property
    def proxy_key(self) -> Path:
        return self.secrets / "master.key"

    @property
    def mirror_sign_key(self) -> Path:
        return self.certs / "mirror-sign.key"

    @property
    def mirror_verify_key(self) -> Path:
        return self.certs / "mirror-sign.pub"

    def ensure(self) -> None:
        for p in (
            self.home,
            self.config_dir,
            self.work,
            self.work / "board",
            self.work / "ventures",
            self.work / "scratch",
            self.logs,
            self.certs,
            self.secrets,
            self.backups,
            self.runtime,
        ):
            p.mkdir(parents=True, exist_ok=True)


def repo_root() -> Path:
    """Checkout containing pyproject.toml (dev or $SABRE_HOME/app)."""
    here = Path(__file__).resolve().parent.parent
    if (here / "pyproject.toml").exists():
        return here
    app = default_home() / "app"
    if (app / "pyproject.toml").exists():
        return app
    return here


def core_dir() -> Path:
    return Path(__file__).resolve().parent
