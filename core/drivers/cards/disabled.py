from __future__ import annotations

from core.drivers import Balance, Card, Charge
from core.errors import CapabilityDisabled


class DisabledCardDriver:
    name = "disabled"

    def issue(self, venture: str, limit_cents: int) -> Card:
        raise CapabilityDisabled("cards", "no-spend mode; sabre setup --step 10")

    def freeze(self, card_id: str) -> None:
        raise CapabilityDisabled("cards")

    def close(self, card_id: str) -> None:
        raise CapabilityDisabled("cards")

    def balance(self, card_id: str) -> Balance:
        raise CapabilityDisabled("cards")

    def list_transactions(self, card_id: str, since: str) -> list[Charge]:
        raise CapabilityDisabled("cards")
