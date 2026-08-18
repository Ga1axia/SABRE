from __future__ import annotations

from typing import Any

from core.db import utcnow
from core.drivers import Charge
from core.errors import CapabilityDisabled, SabreError
from core.ids import new_id


def execute_intent(kind: str, payload: dict[str, Any], drivers: dict[str, Any], conn) -> dict[str, Any]:
    if kind in {"research", "code"}:
        return {"ok": True, "note": "no external effect"}
    if kind == "spend":
        cards = drivers.get("cards")
        if cards is None:
            raise CapabilityDisabled("cards")
        amount = int(payload.get("amount_cents") or 0)
        venture_id = payload.get("venture_id")
        card_id = payload.get("card_id")
        if not card_id and venture_id:
            row = conn.execute("SELECT card_id FROM ventures WHERE id=?", (venture_id,)).fetchone()
            card_id = row["card_id"] if row else None
        if not card_id:
            limit = int(payload.get("limit_cents") or 40_000)
            card = cards.issue(str(venture_id or "unassigned"), limit)
            card_id = card.id
            conn.execute(
                """INSERT INTO cards(id, venture_id, provider_ref, limit_cents, spent_cents, status, issued_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (card.id, venture_id, card.provider_ref, card.limit_cents, 0, "active", utcnow()),
            )
            if venture_id:
                conn.execute("UPDATE ventures SET card_id=? WHERE id=?", (card_id, venture_id))
        charge_id = new_id("CH")
        if hasattr(cards, "record_transaction"):
            cards.record_transaction(
                card_id,
                Charge(id=charge_id, amount_cents=amount, occurred_at=utcnow(), card_id=card_id),
            )
        tx_id = new_id("TX")
        conn.execute(
            """INSERT INTO transactions(
                id, venture_id, intent_id, direction, amount_cents, currency, category, source,
                card_id, external_id, occurred_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tx_id,
                venture_id,
                payload.get("intent_id"),
                "debit",
                amount,
                payload.get("currency") or "USD",
                payload.get("category") or "unknown",
                "gate",
                card_id,
                charge_id,
                utcnow(),
            ),
        )
        conn.execute(
            "UPDATE cards SET spent_cents=spent_cents+? WHERE id=?",
            (amount, card_id),
        )
        return {"ok": True, "transaction_id": tx_id, "card_id": card_id, "external_id": charge_id}
    if kind == "deploy":
        hosting = drivers.get("hosting")
        if hosting is None:
            raise CapabilityDisabled("hosting")
        dep = hosting.deploy(payload.get("path") or ".", payload.get("project") or "venture")
        return {"ok": True, "deployment": dep.id, "url": dep.url}
    if kind == "publish":
        return {"ok": True, "note": "publish recorded"}
    if kind == "outreach":
        return {"ok": True, "note": "outreach recorded"}
    if kind == "account":
        raise SabreError("account intents require operator approval", remedy="see #approvals")
    if kind == "core_change":
        raise SabreError("core_change never auto-executes")
    raise SabreError(f"no executor for {kind}")
