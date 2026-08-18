from __future__ import annotations

import json
from collections.abc import Mapping

from core.drivers import Charge, Event, Refund
from core.drivers.cards.registry import is_issued
from core.errors import CapabilityDisabled


class MemoryPaymentDriver:
    """Pairs with MemoryCardDriver. Internal payers are issued SABRE cards."""

    name = "memory"

    def __init__(self) -> None:
        self._charges: list[Charge] = []
        self._refunds: list[Refund] = []

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> Event | None:
        try:
            data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except json.JSONDecodeError as exc:
            raise CapabilityDisabled("payments", f"invalid webhook: {exc}") from exc
        kind = str(data.get("kind") or "charge")
        return Event(kind=kind, payload=dict(data.get("payload") or data))

    def record_charge(self, charge: Charge) -> None:
        self._charges.append(charge)

    def record_refund(self, refund: Refund) -> None:
        self._refunds.append(refund)

    def list_charges(self, since: str) -> list[Charge]:
        return [c for c in self._charges if (c.occurred_at or "") >= since]

    def refunds(self, since: str) -> list[Refund]:
        return [r for r in self._refunds if (r.occurred_at or "") >= since]

    def is_internal_payer(self, charge: Charge) -> bool:
        return is_issued(charge.card_id) or is_issued(charge.payer_ref)
