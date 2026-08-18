"""Encrypted Tier-2 store. Values never appear in the JSON file or any list API."""

from __future__ import annotations

import json
import secrets
import stat
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core.paths import Paths


def _fernet(paths: Paths) -> Fernet:
    paths.secrets.mkdir(parents=True, exist_ok=True)
    if not paths.proxy_key.exists():
        paths.proxy_key.write_bytes(Fernet.generate_key())
        try:
            paths.proxy_key.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return Fernet(paths.proxy_key.read_bytes())


def _load(paths: Paths) -> dict[str, Any]:
    if not paths.proxy_store.exists():
        return {"secrets": {}}
    return json.loads(paths.proxy_store.read_text(encoding="utf-8"))


def _save(paths: Paths, data: dict[str, Any]) -> None:
    paths.proxy_store.parent.mkdir(parents=True, exist_ok=True)
    paths.proxy_store.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        paths.proxy_store.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def list_secrets(paths: Paths) -> list[dict[str, Any]]:
    data = _load(paths)
    out = []
    for name, row in (data.get("secrets") or {}).items():
        out.append(
            {
                "name": name,
                "tier": row.get("tier", 2),
                "uses": row.get("uses", 0),
                "last_used": row.get("last_used"),
                "error_rate": row.get("error_rate", 0),
                "token": row.get("token"),
            }
        )
    return sorted(out, key=lambda r: r["name"])


def add_secret(paths: Paths, name: str, value: str, tier: int = 2) -> str:
    data = _load(paths)
    token = "pt_" + secrets.token_urlsafe(24)
    blob = _fernet(paths).encrypt(value.encode("utf-8")).decode("ascii")
    data.setdefault("secrets", {})[name] = {
        "tier": tier,
        "uses": 0,
        "last_used": None,
        "error_rate": 0,
        "token": token,
        "ciphertext": blob,
    }
    _save(paths, data)
    return token


def rotate_secret(paths: Paths, name: str, value: str) -> str:
    data = _load(paths)
    row = (data.get("secrets") or {}).get(name)
    if not row:
        return add_secret(paths, name, value)
    row["ciphertext"] = _fernet(paths).encrypt(value.encode("utf-8")).decode("ascii")
    row["token"] = "pt_" + secrets.token_urlsafe(24)
    _save(paths, data)
    return row["token"]


def get_value(paths: Paths, name: str) -> str | None:
    """Proxy/gate only. Never expose through dashboard, agent API, or list_secrets."""
    data = _load(paths)
    row = (data.get("secrets") or {}).get(name)
    if not row:
        return None
    try:
        value = _fernet(paths).decrypt(row["ciphertext"].encode("ascii")).decode("utf-8")
    except (InvalidToken, KeyError, ValueError):
        return None
    row["uses"] = int(row.get("uses") or 0) + 1
    row["last_used"] = datetime.now(UTC).isoformat()
    data.setdefault("secrets", {})[name] = row
    _save(paths, data)
    return value


def get_value_by_token(paths: Paths, token: str) -> str | None:
    if not token:
        return None
    data = _load(paths)
    for name, row in (data.get("secrets") or {}).items():
        if row.get("token") == token:
            return get_value(paths, name)
    return None


def names(paths: Paths) -> list[str]:
    return [r["name"] for r in list_secrets(paths)]
