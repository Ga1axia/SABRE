from __future__ import annotations

import json

import pytest

from core.db import connect, utcnow
from core.drivers import Charge
from core.drivers.cards.disabled import DisabledCardDriver
from core.drivers.cards.memory import MemoryCardDriver
from core.drivers.cards.registry import reset
from core.drivers.hosting.disabled import DisabledHostingDriver
from core.drivers.payments.memory import MemoryPaymentDriver
from core.errors import CapabilityDisabled
from core.hooks.ingest import ingest_payment


def test_cards_disabled_raises():
    with pytest.raises(CapabilityDisabled):
        DisabledCardDriver().issue("geo-audit", 10_000)


def test_hosting_disabled_raises():
    with pytest.raises(CapabilityDisabled):
        DisabledHostingDriver().deploy(".", "demo")


def test_internal_card_payment_is_not_revenue(sabre_home):
    reset()
    cards = MemoryCardDriver()
    pay = MemoryPaymentDriver()
    card = cards.issue("geo-audit", 10_000)
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO cards(id, venture_id, provider_ref, limit_cents, spent_cents, status, issued_at)
           VALUES (?,?,?,?,?,?,?)""",
        (card.id, None, card.provider_ref, card.limit_cents, 0, "active", utcnow()),
    )
    conn.commit()
    conn.close()
    event = pay.verify_webhook(
        json.dumps(
            {
                "kind": "charge",
                "payload": {
                    "amount_cents": 5000,
                    "card_id": card.id,
                    "payer_ref": card.provider_ref,
                    "external_id": "ch_self",
                },
            }
        ).encode(),
        {},
    )
    assert event is not None
    charge = Charge(
        id="ch_self",
        amount_cents=5000,
        occurred_at="t",
        payer_ref=card.provider_ref,
        card_id=card.id,
    )
    assert pay.is_internal_payer(charge) is True
    assert ingest_payment(sabre_home, pay, event) == "ignored"
    conn = connect(sabre_home.db)
    n = conn.execute("SELECT COUNT(*) FROM transactions WHERE direction='credit'").fetchone()[0]
    conn.close()
    assert n == 0


def test_external_payment_counts_as_revenue(sabre_home):
    reset()
    pay = MemoryPaymentDriver()
    event = pay.verify_webhook(
        json.dumps(
            {
                "kind": "charge",
                "payload": {
                    "amount_cents": 1200,
                    "card_id": "cus_external",
                    "payer_ref": "cus_external",
                    "external_id": "ch_ext",
                },
            }
        ).encode(),
        {},
    )
    assert ingest_payment(sabre_home, pay, event) == "credited"
    conn = connect(sabre_home.db)
    n = conn.execute("SELECT COUNT(*) FROM transactions WHERE direction='credit'").fetchone()[0]
    conn.close()
    assert n == 1
