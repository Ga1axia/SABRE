"""Lithic issuer driver — authorizations are simulated/settled at Lithic, not in-process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.db import utcnow
from core.drivers import Balance, Card, Charge
from core.drivers.cards.lithic_client import LithicClient, LithicDeclined
from core.errors import SabreError
from core.gate.card_secrets import resolve_card_pan, store_card_pan
from core.ids import new_id
from core.paths import Paths, default_home


class LithicCardDriver:
    name = "lithic"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, sabre_home: str | None = None):
        self._client = LithicClient(api_key, base_url=base_url)
        home = Path(sabre_home) if sabre_home else default_home()
        self._paths = Paths(home)
        self._index_path = self._paths.secrets / "lithic-index.json"
        self._cards: dict[str, dict[str, Any]] = self._load_index()

    def issue(self, venture: str, limit_cents: int) -> Card:
        created = self._client.create_card(spend_limit_cents=int(limit_cents))
        token = str(created.get("token") or created.get("card_token") or "")
        pan = str(created.get("pan") or "")
        if not token or not pan:
            raise SabreError("Lithic card response missing token or pan", remedy="check Lithic sandbox account")
        cid = new_id("CARD")
        provider_ref = f"lithic:{token}"
        card = Card(id=cid, provider_ref=provider_ref, limit_cents=int(limit_cents))
        store_card_pan(self._paths, cid, pan)
        self._cards[cid] = {
            "venture": venture,
            "token": token,
            "limit_cents": int(limit_cents),
            "issued_at": utcnow(),
        }
        self._save_index()
        return card

    def authorize(
        self,
        card_id: str,
        amount_cents: int,
        *,
        provider_ref: str = "",
        merchant: str = "SABRE",
    ) -> Charge:
        meta = self._resolve(card_id, provider_ref)
        pan = resolve_card_pan(self._paths, card_id)
        if not pan:
            raise SabreError(f"PAN missing for card {card_id}", remedy="re-issue card via gate spend")
        result = self._client.simulate_authorize(pan=pan, amount_cents=int(amount_cents), descriptor=merchant)
        ext_id = str(result.get("token") or result.get("transaction_token") or new_id("LT"))
        occurred = str(result.get("created") or utcnow())
        return Charge(id=ext_id, amount_cents=int(amount_cents), occurred_at=occurred, card_id=card_id)

    def freeze(self, card_id: str) -> None:
        meta = self._resolve(card_id, "")
        self._client.freeze_card(meta["token"])

    def close(self, card_id: str) -> None:
        meta = self._cards.get(card_id)
        if meta:
            self._client.close_card(meta["token"])
            self._cards.pop(card_id, None)
            self._save_index()

    def balance(self, card_id: str) -> Balance:
        meta = self._resolve(card_id, "")
        token = meta["token"]
        since = "1970-01-01T00:00:00"
        spent = sum(int(row.get("amount") or row.get("settled_amount") or 0) for row in self._client.list_transactions(card_token=token, since=since))
        limit = int(meta.get("limit_cents") or 0)
        return Balance(spent_cents=spent, remaining_cents=max(0, limit - spent), limit_cents=limit)

    def list_transactions(self, card_id: str, since: str) -> list[Charge]:
        meta = self._resolve(card_id, "")
        rows = self._client.list_transactions(card_token=meta["token"], since=since or "1970-01-01T00:00:00")
        out: list[Charge] = []
        for row in rows:
            amount = int(row.get("amount") or row.get("settled_amount") or 0)
            if amount <= 0:
                continue
            ext = str(row.get("token") or row.get("transaction_token") or new_id("LT"))
            occurred = str(row.get("created") or row.get("updated") or utcnow())
            out.append(Charge(id=ext, amount_cents=amount, occurred_at=occurred, card_id=card_id))
        return out

    def _resolve(self, card_id: str, provider_ref: str) -> dict[str, Any]:
        if card_id in self._cards:
            return self._cards[card_id]
        if provider_ref.startswith("lithic:"):
            token = provider_ref.split(":", 1)[1]
            for meta in self._cards.values():
                if meta.get("token") == token:
                    return meta
        raise SabreError(f"unknown Lithic card {card_id}", remedy="re-issue card via gate spend")

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self._index_path.exists():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_index(self) -> None:
        self._paths.secrets.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(json.dumps(self._cards, indent=2) + "\n", encoding="utf-8")


__all__ = ["LithicCardDriver", "LithicDeclined"]
