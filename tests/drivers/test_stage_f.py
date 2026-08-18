from __future__ import annotations

import json

from core.db import connect, utcnow
from core.drivers import Charge
from core.drivers.cards.memory import MemoryCardDriver
from core.drivers.cards.registry import reset
from core.drivers.payments.memory import MemoryPaymentDriver
from core.drivers.payments.stripe import StripePaymentDriver
from core.gate.ledger import spend_frozen
from core.gate.reconcile import reconcile
from core.hooks.ingest import ingest_payment


def test_stripe_internal_payer_detects_sabre_issued_metadata():
    reset()
    cards = MemoryCardDriver()
    card = cards.issue("geo-audit", 10_000)
    pay = StripePaymentDriver(secret_key="sk_test_x")
    charge = Charge(
        id="ch_int",
        amount_cents=500,
        occurred_at="t",
        payer_ref=f"lithic:tok",
        card_id=card.id,
    )
    charge.metadata = {"sabre_issued": "true", "sabre_card_id": card.id}  # type: ignore[attr-defined]
    assert pay.is_internal_payer(charge) is True


def test_stripe_sabre_card_payment_not_revenue(sabre_home):
    reset()
    cards = MemoryCardDriver()
    pay = StripePaymentDriver(secret_key="sk_test_x")
    card = cards.issue("geo-audit", 10_000)
    from core.drivers import Event

    payload = {
        "amount_cents": 5000,
        "card_id": card.id,
        "payer_ref": card.provider_ref,
        "external_id": "ch_self",
    }
    probe = Charge(
        id="ch_self",
        amount_cents=5000,
        occurred_at=utcnow(),
        payer_ref=card.provider_ref,
        card_id=card.id,
    )
    assert pay.is_internal_payer(probe) is True
    assert ingest_payment(sabre_home, pay, Event(kind="charge", payload=payload)) == "ignored"
    conn = connect(sabre_home.db)
    n = conn.execute("SELECT COUNT(*) FROM transactions WHERE direction='credit'").fetchone()[0]
    conn.close()
    assert n == 0


def test_external_stripe_charge_counts_as_revenue(sabre_home):
    reset()
    pay = StripePaymentDriver(secret_key="sk_test_x")
    charge = Charge(id="ch_ext", amount_cents=1200, occurred_at=utcnow(), payer_ref="cus_external", card_id="")
    assert pay.is_internal_payer(charge) is False
    from core.drivers import Event

    assert ingest_payment(
        sabre_home,
        pay,
        Event(
            kind="charge",
            payload={"amount_cents": 1200, "external_id": "ch_ext", "payer_ref": "cus_external"},
        ),
    ) == "credited"


def test_reconcile_card_divergence_freezes_spend(sabre_home):
    reset()
    conn = connect(sabre_home.db)
    cards = MemoryCardDriver()
    card = cards.issue("v", 5000)
    charge = cards.authorize(card.id, 1200, provider_ref=card.provider_ref)
    conn.execute(
        """INSERT INTO cards(id, venture_id, provider_ref, limit_cents, spent_cents, status, issued_at)
           VALUES (?,?,?,?,?,?,?)""",
        (card.id, None, card.provider_ref, card.limit_cents, 1200, "active", utcnow()),
    )
    conn.execute(
        """INSERT INTO transactions(
               id, venture_id, direction, amount_cents, currency, category, source, card_id, external_id, occurred_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("TX1", None, "debit", 1200, "USD", "domains", "gate", card.id, charge.id, utcnow()),
    )
    conn.commit()
    extra = Charge(id="prov_only", amount_cents=500, occurred_at=utcnow(), card_id=card.id)
    cards.record_transaction(card.id, extra)
    report = reconcile({"cards": cards, "payments": None}, conn, paths=sabre_home)
    assert report["ok"] is False
    assert any(d.get("kind") == "card_missing_in_ledger" for d in report["divergences"])
    assert spend_frozen(sabre_home) is True
    conn.close()


def test_reconcile_ignores_sub_tolerance_card_gap(sabre_home):
    reset()
    conn = connect(sabre_home.db)
    cards = MemoryCardDriver()
    card = cards.issue("v", 5000)
    tiny = Charge(id="tiny", amount_cents=50, occurred_at=utcnow(), card_id=card.id)
    cards.record_transaction(card.id, tiny)
    conn.execute(
        """INSERT INTO cards(id, venture_id, provider_ref, limit_cents, spent_cents, status, issued_at)
           VALUES (?,?,?,?,?,?,?)""",
        (card.id, None, card.provider_ref, 5000, 0, "active", utcnow()),
    )
    conn.commit()
    report = reconcile({"cards": cards, "payments": None}, conn, paths=sabre_home)
    assert report["ok"] is True
    conn.close()
