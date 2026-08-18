from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.config import load_settings, write_yaml
from core.db import connect, utcnow
from core.drivers import Charge
from core.drivers.cards.lithic import LithicCardDriver
from core.drivers.cards.lithic_client import LithicClient
from core.drivers.cards.memory import MemoryCardDriver
from core.drivers.payments.memory import MemoryPaymentDriver
from core.drivers.payments.stripe import StripePaymentDriver
from core.gate.approvals import format_approval_message
from core.gate.ledger import spend_frozen
from core.gate.reconcile import reconcile
from core.gate.review import ReviewResult, review_intent
from core.gate.submit import submit_intent
from core.hooks.ingest import ingest_payment
from core.loop.discover import discover
from core.services.control import start_all
from core.setup.checks import check_pan_leak


def test_pan_doctor_fails_on_planted_pan(sabre_home):
    from core.config import load_settings

    leak = sabre_home.runtime / "planted-pan.txt"
    leak.write_text("backup card 4111111111111111\n", encoding="utf-8")
    settings = load_settings(sabre_home)
    ok, msg = check_pan_leak(sabre_home, settings)
    assert ok is False
    assert "PAN" in msg or "Luhn" in msg


def test_pan_doctor_passes_after_planted_pan_removed(sabre_home):
    from core.config import load_settings

    leak = sabre_home.runtime / "planted-pan.txt"
    leak.write_text("backup card 4111111111111111\n", encoding="utf-8")
    settings = load_settings(sabre_home)
    assert check_pan_leak(sabre_home, settings)[0] is False
    leak.unlink()
    ok, msg = check_pan_leak(sabre_home, settings)
    assert ok is True
    assert "pan-shaped" in msg.lower()


def test_lithic_issue_returns_reference_not_pan(sabre_home, monkeypatch):
    client = MagicMock(spec=LithicClient)
    client.create_card.return_value = {"token": "tok_1", "pan": "4111111111111111"}
    client.list_transactions.return_value = []
    monkeypatch.setattr("core.drivers.cards.lithic.LithicClient", lambda *a, **k: client)
    driver = LithicCardDriver(api_key="test", sabre_home=str(sabre_home.home))
    card = driver.issue("geo-audit", 1000)
    assert card.id.startswith("CARD")
    assert card.provider_ref == "lithic:tok_1"
    assert not hasattr(card, "pan")
    index_path = sabre_home.secrets / "lithic-index.json"
    assert index_path.exists()
    index_text = index_path.read_text(encoding="utf-8")
    assert "pan" not in index_text.lower()
    assert "4111111111111111" not in index_text
    runtime_cards = sabre_home.runtime / "lithic-cards.json"
    assert not runtime_cards.exists()


def test_discover_unreachable_writes_nothing_and_alerts(sabre_home, monkeypatch):
    alerts: list[str] = []
    monkeypatch.setattr("core.loop.discover.alert_once", lambda paths, key, msg, channel: alerts.append(msg) or True)
    with patch("core.loop.discover._mine_hn", side_effect=ConnectionError("network down")):
        out = discover(sabre_home)
    assert out["written"] == []
    assert out["errors"]
    assert not list((sabre_home.work / "opportunities").glob("*.json"))
    assert alerts
    assert "unreachable" in alerts[0].lower()


def test_review_unavailable_empty_dissent_and_banner(sabre_home, monkeypatch):
    monkeypatch.delenv("SABRE_REVIEW_KEY", raising=False)
    settings = load_settings(sabre_home)
    review = review_intent(settings, {"kind": "spend", "rationale": "ads", "payload": {}}, "red")
    assert review.dissent == ""
    assert review.available is False
    msg = format_approval_message("I1", "red", {"kind": "spend", "rationale": "ads"}, review)
    assert "REVIEW UNAVAILABLE" in msg
    assert "dissent:" not in msg.lower()


def test_start_refuses_cards_without_reviewer(sabre_home, monkeypatch):
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "drivers": {"cards": {"name": "memory", "enabled": True}},
            "alerts": {"fallback": {"name": "memory", "to": "ops@example.com"}},
        },
    )
    monkeypatch.delenv("SABRE_REVIEW_KEY", raising=False)
    settings = load_settings(sabre_home)
    monkeypatch.setattr("core.services.control.start_service", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="SABRE_REVIEW_KEY"):
        start_all(settings)


def test_stripe_issued_card_ignored_without_metadata(sabre_home):
    cards = MemoryCardDriver()
    pay = StripePaymentDriver(secret_key="sk_test_x")
    card = cards.issue("geo-audit", 10_000)
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO cards(id, venture_id, provider_ref, limit_cents, spent_cents, status, issued_at)
           VALUES (?,?,?,?,?,?,?)""",
        (card.id, None, card.provider_ref, card.limit_cents, 0, "active", utcnow()),
    )
    conn.commit()
    conn.close()
    from core.drivers import Event

    payload = {
        "amount_cents": 5000,
        "card_id": card.id,
        "payer_ref": "cus_attacker_forged",
        "external_id": "ch_self",
    }
    assert ingest_payment(sabre_home, pay, Event(kind="charge", payload=payload)) == "ignored"
    conn = connect(sabre_home.db)
    n = conn.execute("SELECT COUNT(*) FROM transactions WHERE direction='credit'").fetchone()[0]
    conn.close()
    assert n == 0


def test_reconcile_payment_divergence_flags(sabre_home):
    conn = connect(sabre_home.db)
    pay = MemoryPaymentDriver()
    pay.record_charge(Charge(id="ch_rev_only", amount_cents=1200, occurred_at=utcnow(), payer_ref="cus"))
    report = reconcile({"cards": None, "payments": pay}, conn, paths=sabre_home)
    assert report["ok"] is False
    assert any(d.get("kind") == "payment_missing_in_ledger" for d in report["divergences"])
    conn.close()


def test_reconcile_ignores_sub_tolerance_payment_gap(sabre_home):
    conn = connect(sabre_home.db)
    pay = MemoryPaymentDriver()
    tiny = Charge(id="ch_tiny", amount_cents=50, occurred_at=utcnow(), payer_ref="cus")
    pay.record_charge(tiny)
    report = reconcile({"cards": None, "payments": pay}, conn, paths=sabre_home)
    assert report["ok"] is True
    conn.close()


def test_held_intent_posts_review_unavailable_not_dissent_prose(sabre_home, monkeypatch):
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "envelopes": {"spend": {"daily_max": 5000, "monthly_max": 50000}},
            "drivers": {"cards": {"name": "memory", "enabled": True}},
        },
    )
    monkeypatch.delenv("SABRE_REVIEW_KEY", raising=False)
    posted: list[str] = []
    monkeypatch.setattr("core.gate.approvals.alert", lambda paths, msg, channel: posted.append(msg) or True)
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    result = submit_intent(
        settings,
        conn,
        {
            "kind": "core_change",
            "payload": {"path": "core/gate/classify.py"},
            "rationale": "rewrite policy",
        },
    )
    conn.commit()
    row = conn.execute("SELECT dissent FROM intents WHERE id=?", (result["id"],)).fetchone()
    conn.close()
    assert result["classification"] == "red"
    assert row["dissent"] in (None, "")
    assert posted
    assert "REVIEW UNAVAILABLE" in posted[0]
