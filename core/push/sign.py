"""Ed25519 snapshot signatures. The mirror has the public key only."""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.paths import Paths


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def ensure_keys(paths: Paths) -> None:
    paths.certs.mkdir(parents=True, exist_ok=True)
    if paths.mirror_sign_key.exists() and paths.mirror_verify_key.exists():
        return
    key = Ed25519PrivateKey.generate()
    paths.mirror_sign_key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    paths.mirror_verify_key.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def sign_snapshot(paths: Paths, snapshot: dict[str, Any]) -> dict[str, Any]:
    ensure_keys(paths)
    key = serialization.load_pem_private_key(paths.mirror_sign_key.read_bytes(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    sig = base64.b64encode(key.sign(_canonical(snapshot))).decode("ascii")
    return {"snapshot": snapshot, "signature": sig, "alg": "ed25519"}


def verify_envelope(public_pem: str, envelope: dict[str, Any]) -> bool:
    sig_b64 = envelope.get("signature")
    snap = envelope.get("snapshot")
    if not sig_b64 or snap is None:
        return False
    try:
        pub = serialization.load_pem_public_key(public_pem.encode("utf-8"))
        assert isinstance(pub, Ed25519PublicKey)
        pub.verify(base64.b64decode(sig_b64), _canonical(snap))
        return True
    except Exception:
        return False
