"""Issued-card registry shared by the in-memory card and payment drivers."""

from __future__ import annotations

from core.drivers import Card

ISSUED: dict[str, Card] = {}
CHARGES: dict[str, list] = {}


def reset() -> None:
    ISSUED.clear()
    CHARGES.clear()


def remember(card: Card) -> None:
    ISSUED[card.id] = card
    ISSUED[card.provider_ref] = card


def is_issued(ref: str) -> bool:
    return bool(ref) and ref in ISSUED
