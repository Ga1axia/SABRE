from __future__ import annotations

from core.drivers import Balance, Card, Charge
from core.drivers.cards.registry import CHARGES, ISSUED, remember
from core.db import utcnow
from core.ids import new_id


class MemoryCardDriver:
    """In-process issuer used for contract tests and local no-network charging."""

    name = "memory"

    def __init__(self) -> None:
        pass

    def issue(self, venture: str, limit_cents: int) -> Card:
        cid = new_id("CARD")
        card = Card(id=cid, provider_ref=f"mem:{venture}:{cid}", limit_cents=limit_cents)
        remember(card)
        return card

    def freeze(self, card_id: str) -> None:
        return None

    def close(self, card_id: str) -> None:
        ISSUED.pop(card_id, None)

    def balance(self, card_id: str) -> Balance:
        card = ISSUED.get(card_id)
        limit = card.limit_cents if card else 0
        spent = sum(c.amount_cents for c in CHARGES.get(card_id, []))
        return Balance(spent_cents=spent, remaining_cents=limit - spent, limit_cents=limit)

    def authorize(
        self,
        card_id: str,
        amount_cents: int,
        *,
        provider_ref: str = "",
        merchant: str = "",
    ) -> Charge:
        bal = self.balance(card_id)
        if amount_cents > bal.remaining_cents:
            from core.errors import SabreError

            raise SabreError("memory issuer declined: over limit", remedy="use lithic driver for provider-side limits")
        charge = Charge(id=new_id("CH"), amount_cents=int(amount_cents), occurred_at=utcnow(), card_id=card_id)
        self.record_transaction(card_id, charge)
        return charge

    def record_transaction(self, card_id: str, charge: Charge) -> None:
        CHARGES.setdefault(card_id, []).append(charge)

    def list_transactions(self, card_id: str, since: str) -> list[Charge]:
        return [c for c in CHARGES.get(card_id, []) if (c.occurred_at or "") >= since]
