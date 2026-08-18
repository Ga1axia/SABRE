"""Tier-2 PAN storage. Gate-only; never list or expose through agent APIs."""

from __future__ import annotations

from core.paths import Paths
from core.proxy.store import add_secret, get_value, rotate_secret


def _secret_name(card_id: str) -> str:
    return f"card_pan:{card_id}"


def store_card_pan(paths: Paths, card_id: str, pan: str) -> None:
    name = _secret_name(card_id)
    if get_value(paths, name):
        rotate_secret(paths, name, pan)
    else:
        add_secret(paths, name, pan, tier=2)


def resolve_card_pan(paths: Paths, card_id: str) -> str | None:
    return get_value(paths, _secret_name(card_id))
