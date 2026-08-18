from __future__ import annotations

from collections.abc import Mapping

from core.drivers import Charge, Event, Refund
from core.errors import CapabilityDisabled


class DisabledPaymentDriver:
    name = "disabled"

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> Event | None:
        raise CapabilityDisabled("payments", "revenue tracking disabled; sabre setup --step 11")

    def list_charges(self, since: str) -> list[Charge]:
        raise CapabilityDisabled("payments")

    def refunds(self, since: str) -> list[Refund]:
        raise CapabilityDisabled("payments")

    def is_internal_payer(self, charge: Charge) -> bool:
        # Contract: must not unconditionally return False. With no issuer, we cannot
        # tell — treat every charge as potentially internal so the fitness function
        # does not credit SABRE-issued cards as revenue.
        return True
