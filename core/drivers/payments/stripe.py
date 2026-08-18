"""Stripe payment driver — revenue ingestion with circular-revenue guard."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Mapping

import httpx

from core.drivers import Charge, Event, Refund
from core.drivers.cards.registry import is_issued
from core.errors import CapabilityDisabled, SabreError


class StripePaymentDriver:
    name = "stripe"

    def __init__(self, *, secret_key: str | None = None, webhook_secret: str | None = None):
        self.secret_key = secret_key or os.environ.get("SABRE_STRIPE_SECRET_KEY") or ""
        self.webhook_secret = webhook_secret or os.environ.get("SABRE_STRIPE_WEBHOOK_SECRET") or ""
        if not self.secret_key:
            raise SabreError("Stripe secret key missing", remedy="set SABRE_STRIPE_SECRET_KEY")

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> Event | None:
        if not self.webhook_secret:
            raise CapabilityDisabled("payments", "SABRE_STRIPE_WEBHOOK_SECRET missing")
        sig = headers.get("Stripe-Signature") or headers.get("stripe-signature") or ""
        if not self._verify_signature(body, sig):
            raise CapabilityDisabled("payments", "invalid Stripe webhook signature")
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        kind = str(data.get("type") or "charge")
        obj = ((data.get("data") or {}).get("object") or {}) if isinstance(data.get("data"), dict) else {}
        payload = self._charge_from_stripe(obj) if obj else {}
        return Event(kind=kind, payload=payload)

    def list_charges(self, since: str) -> list[Charge]:
        rows: list[Charge] = []
        created_gte = int(time.mktime(time.strptime(since[:19], "%Y-%m-%dT%H:%M:%S"))) if since else 0
        params: dict[str, str | int] = {"limit": 100}
        if created_gte:
            params["created[gte]"] = created_gte
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                "https://api.stripe.com/v1/charges",
                params=params,
                auth=(self.secret_key, ""),
            )
        if r.status_code >= 400:
            raise SabreError(f"Stripe list charges failed: {r.status_code}")
        data = r.json()
        for obj in data.get("data") or []:
            if isinstance(obj, dict):
                rows.append(self._charge_from_stripe(obj))
        return rows

    def refunds(self, since: str) -> list[Refund]:
        return []

    def is_internal_payer(self, charge: Charge) -> bool:
        meta = getattr(charge, "metadata", None)
        if isinstance(meta, dict):
            if meta.get("sabre_issued") in {True, "true", "1", 1}:
                return True
            if meta.get("sabre_card_id") and is_issued(str(meta["sabre_card_id"])):
                return True
            if meta.get("lithic_token") and is_issued(f"lithic:{meta['lithic_token']}"):
                return True
        if is_issued(charge.card_id) or is_issued(charge.payer_ref):
            return True
        payer = charge.payer_ref or ""
        if payer.startswith("lithic:") and is_issued(payer):
            return True
        return False

    def _charge_from_stripe(self, obj: dict) -> Charge:
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        amount = int(obj.get("amount") or 0)
        created = int(obj.get("created") or 0)
        occurred = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(created)) if created else ""
        payer = str(meta.get("lithic_token") or meta.get("sabre_card_id") or obj.get("customer") or "")
        card_id = str(meta.get("sabre_card_id") or "")
        charge = Charge(
            id=str(obj.get("id") or ""),
            amount_cents=amount,
            occurred_at=occurred,
            payer_ref=payer if payer else str(obj.get("id") or ""),
            card_id=card_id,
        )
        charge.metadata = meta  # type: ignore[attr-defined]
        return charge

    def _verify_signature(self, payload: bytes, header: str) -> bool:
        parts = {}
        for item in header.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                parts[k.strip()] = v.strip()
        ts = parts.get("t")
        v1 = parts.get("v1")
        if not ts or not v1:
            return False
        signed = f"{ts}.{payload.decode('utf-8')}".encode()
        digest = hmac.new(self.webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, v1)
