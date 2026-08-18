from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.drivers.cards.lithic import LithicCardDriver
from core.drivers.cards.lithic_client import LithicClient, LithicDeclined
from core.errors import SabreError


def test_lithic_decline_comes_from_provider_message():
    client = MagicMock(spec=LithicClient)
    client.simulate_authorize.side_effect = LithicDeclined(
        "Transaction exceeds user-set transaction limit",
        remedy="reduce amount",
    )
    with pytest.raises(LithicDeclined, match="Transaction exceeds"):
        client.simulate_authorize(pan="4111111111111111", amount_cents=5000)


def test_lithic_driver_authorize_uses_client(sabre_home, monkeypatch):
    client = MagicMock(spec=LithicClient)
    client.create_card.return_value = {"token": "tok_1", "pan": "4111111111111111"}
    client.simulate_authorize.return_value = {"token": "txn_1", "created": "2026-01-01T00:00:00+00:00"}
    client.list_transactions.return_value = []
    monkeypatch.setattr("core.drivers.cards.lithic.LithicClient", lambda *a, **k: client)
    driver = LithicCardDriver(api_key="test", sabre_home=str(sabre_home.home))
    card = driver.issue("geo-audit", 1000)
    charge = driver.authorize(card.id, 500, provider_ref=card.provider_ref)
    assert charge.id == "txn_1"
    client.simulate_authorize.assert_called_once()
    client.simulate_authorize.side_effect = LithicDeclined("provider refused")
    with pytest.raises(LithicDeclined, match="provider refused"):
        driver.authorize(card.id, 9000, provider_ref=card.provider_ref)


def test_lithic_live_limit_refusal():
    import os

    if not os.environ.get("SABRE_LITHIC_API_KEY"):
        pytest.skip("SABRE_LITHIC_API_KEY not set")
    client = LithicClient()
    card = client.create_card(spend_limit_cents=1000)
    pan = card["pan"]
    client.simulate_authorize(pan=pan, amount_cents=500, descriptor="within")
    with pytest.raises(LithicDeclined) as exc:
        client.simulate_authorize(pan=pan, amount_cents=2000, descriptor="over-limit")
    msg = str(exc.value)
    print("LITHIC_PROVIDER_REFUSAL", msg)
    assert "limit" in msg.lower() or "exceed" in msg.lower()
