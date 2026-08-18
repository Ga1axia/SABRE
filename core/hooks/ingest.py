"""Revenue ingest. Credits and refunds are written only here and by gate reconcile."""

from __future__ import annotations

from core.db import connect, utcnow
from core.drivers import Charge, Event, Refund
from core.gate.refunds import apply_refund
from core.ids import new_id
from core.paths import Paths


def ingest_payment(paths: Paths, driver, event: Event) -> str:
    """Return ignored | credited | refunded | skipped."""
    payload = event.payload or {}
    if event.kind == "refund":
        refund = Refund(
            id=str(payload.get("external_id") or payload.get("id") or ""),
            charge_id=str(payload.get("charge_id") or payload.get("payment_id") or ""),
            amount_cents=int(payload.get("amount_cents") or 0),
            occurred_at=str(payload.get("occurred_at") or utcnow()),
        )
        conn = connect(paths.db)
        try:
            apply_refund(conn, refund, source="webhook")
            conn.commit()
        finally:
            conn.close()
        return "refunded"
    if event.kind not in {"charge", "payment"}:
        return "skipped"
    charge = Charge(
        id=str(payload.get("external_id") or payload.get("id") or ""),
        amount_cents=int(payload.get("amount_cents") or 0),
        occurred_at=str(payload.get("occurred_at") or utcnow()),
        payer_ref=str(payload.get("payer_ref") or ""),
        card_id=str(payload.get("card_id") or ""),
    )
    if driver.is_internal_payer(charge):
        return "ignored"
    conn = connect(paths.db)
    try:
        conn.execute(
            """INSERT INTO transactions(
                   id, venture_id, intent_id, direction, amount_cents,
                   currency, category, source, external_id, occurred_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                new_id("TX"),
                payload.get("venture_id"),
                None,
                "credit",
                charge.amount_cents,
                payload.get("currency") or "USD",
                "revenue",
                "webhook",
                charge.id or None,
                utcnow(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return "credited"
