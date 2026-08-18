"""Canonical idempotency keys. The gate derives them; the client cannot pick a fresh one."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.errors import SabreError


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_key(intent: dict[str, Any]) -> str:
    body = {
        "kind": intent.get("kind"),
        "payload": intent.get("payload") or {},
        "venture": intent.get("venture") or intent.get("venture_id"),
    }
    digest = hashlib.sha256(_canonical(body)).hexdigest()[:32]
    kind = str(body["kind"] or "unknown")
    venture = str(body["venture"] or "_")
    return f"{kind}:{venture}:{digest}"


def bind_key(intent: dict[str, Any]) -> dict[str, Any]:
    computed = canonical_key(intent)
    supplied = intent.get("idempotency_key")
    if supplied and supplied != computed:
        raise SabreError(
            "idempotency_key does not match payload",
            remedy="omit the key or send the canonical key derived from kind+venture+payload",
        )
    out = dict(intent)
    out["idempotency_key"] = computed
    return out
