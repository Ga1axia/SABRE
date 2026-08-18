"""Intent submit. Classify and insert share one IMMEDIATE transaction."""

from __future__ import annotations

import sqlite3
from typing import Any

from core.config import Settings
from core.db import later, utcnow
from core.drivers.loader import load_driver
from core.errors import CapabilityDisabled, SabreError
from core.gate.classify import classify
from core.gate.execute import execute_intent
from core.gate.idempotency import bind_key
from core.gate.ledger import expire_held_red, get_intent_by_key, insert_intent, ledger_view, spend_frozen
from core.watch.killswitch import is_killed


def begin_immediate(conn: sqlite3.Connection) -> None:
    if conn.isolation_level is not None:
        conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")


def effect_drivers(settings: Settings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for slot in ("cards", "hosting", "payments"):
        spec = settings.drivers.get(slot) or {}
        name = spec.get("name") or "disabled"
        try:
            out[slot] = load_driver(slot, name)
        except Exception:
            out[slot] = None
        if not settings.driver_enabled(slot):
            out[slot] = None
    return out


def submit_intent(settings: Settings, conn: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    paths = settings.paths
    if is_killed(paths):
        return {"error": "kill switch engaged", "state": "refused"}
    try:
        body = bind_key(body)
    except SabreError as exc:
        return {"error": str(exc), "state": "refused"}
    key = body["idempotency_key"]
    begin_immediate(conn)
    expire_held_red(conn, settings.red_expire_days)
    existing = get_intent_by_key(conn, key)
    if existing:
        return {
            "id": existing["id"],
            "classification": existing["classification"],
            "state": existing["state"],
            "replayed": True,
        }
    venture = body.get("venture") or body.get("venture_id")
    view = ledger_view(conn, venture)
    view.spend_frozen = spend_frozen(paths)
    result = classify(
        body,
        envelopes=settings.envelopes,
        ledger=view,
        no_spend=settings.no_spend,
        hosting_enabled=settings.driver_enabled("hosting"),
    )
    review = None
    if result.classification in {"amber", "red"}:
        from core.gate.review import review_intent

        review = review_intent(settings, body, result.classification)
        body["dissent"] = review.dissent or None
    hold_until = None
    if result.classification == "red":
        hold_until = later(settings.red_expire_days * 86400)
    elif result.classification == "amber":
        hold_until = later(int(settings.raw.get("amber_hold_minutes") or 30) * 60)
    iid = insert_intent(conn, body, result.classification, "proposed", hold_until=hold_until)
    state = "proposed"
    if result.classification == "green":
        state = "executed"
    elif result.classification in {"amber", "red"}:
        state = "held"
    if result.classification == "green":
        drivers = effect_drivers(settings)
        payload = dict(body.get("payload") or {})
        payload["intent_id"] = iid
        stored = conn.execute("SELECT venture_id FROM intents WHERE id=?", (iid,)).fetchone()
        payload["venture_id"] = stored["venture_id"] if stored else None
        try:
            exec_result = execute_intent(body["kind"], payload, drivers, conn)
            conn.execute(
                "UPDATE intents SET state='executed', classification=?, executed_at=? WHERE id=?",
                (result.classification, utcnow(), iid),
            )
            return {
                "id": iid,
                "classification": "green",
                "state": "executed",
                "transaction_id": exec_result.get("transaction_id"),
                "reasons": result.reasons,
            }
        except (CapabilityDisabled, SabreError) as exc:
            conn.execute(
                "UPDATE intents SET state='failed', error=? WHERE id=?",
                (str(exc), iid),
            )
            return {
                "id": iid,
                "classification": result.classification,
                "state": "failed",
                "error": str(exc),
            }
    conn.execute(
        "UPDATE intents SET state=?, classification=?, hold_until=? WHERE id=?",
        (state, result.classification, hold_until, iid),
    )
    if result.classification in {"amber", "red"} and review is not None:
        from core.gate.approvals import post_approval

        post_approval(settings, iid, body, result.classification, review, hold_until=hold_until)
    return {
        "id": iid,
        "classification": result.classification,
        "state": state,
        "reasons": result.reasons,
        "hold_until": hold_until,
        "review_available": review.available if review else None,
    }
