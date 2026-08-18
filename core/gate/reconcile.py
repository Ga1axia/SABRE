"""Nightly reconciliation. Divergence freezes spend. Refunds are applied here."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.db import utcnow
from core.errors import CapabilityDisabled
from core.gate.refunds import apply_refund
from core.paths import Paths


def _tolerance_cents(paths: Paths | None) -> int:
    if paths is None:
        return 100
    try:
        from core.config import load_settings

        raw = load_settings(paths).raw.get("reconcile") or {}
        return int(raw.get("tolerance_cents") or 100)
    except Exception:
        return 100


def _debits(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in conn.execute(
        "SELECT external_id, amount_cents FROM transactions WHERE direction='debit' AND external_id IS NOT NULL"
    ):
        out[str(row[0])] = int(row[1])
    return out


def _credits(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in conn.execute(
        "SELECT external_id, amount_cents FROM transactions WHERE direction='credit' AND external_id IS NOT NULL"
    ):
        out[str(row[0])] = int(row[1])
    return out


def reconcile(drivers: dict, conn: sqlite3.Connection, *, paths: Paths | None = None, since: str = "") -> dict:
    since = since or "1970-01-01"
    divergences: list[dict[str, Any]] = []
    skipped: list[str] = []
    applied_refunds = 0
    tolerance = _tolerance_cents(paths)

    cards = drivers.get("cards")
    payments = drivers.get("payments")

    if cards is None:
        skipped.append("cards")
    else:
        try:
            ledger_debits = _debits(conn)
            ledger_ids = set(ledger_debits)
            provider_ids: set[str] = set()
            for row in conn.execute("SELECT id FROM cards"):
                for charge in cards.list_transactions(row[0], since):
                    provider_ids.add(charge.id)
                    if charge.id not in ledger_ids and abs(int(charge.amount_cents)) > tolerance:
                        divergences.append(
                            {
                                "kind": "card_missing_in_ledger",
                                "external_id": charge.id,
                                "amount_cents": charge.amount_cents,
                            }
                        )
                    elif (
                        charge.id in ledger_ids
                        and abs(int(charge.amount_cents) - ledger_debits[charge.id]) > tolerance
                    ):
                        divergences.append(
                            {
                                "kind": "card_amount_mismatch",
                                "external_id": charge.id,
                                "amount_cents": charge.amount_cents,
                                "ledger_cents": ledger_debits[charge.id],
                            }
                        )
            for eid in ledger_ids - provider_ids:
                if eid and ledger_debits.get(eid, 0) > tolerance:
                    divergences.append({"kind": "ledger_debit_absent_at_provider", "external_id": eid})
        except CapabilityDisabled:
            skipped.append("cards")

    if payments is None:
        skipped.append("payments")
    else:
        try:
            for refund in payments.refunds(since):
                apply_refund(conn, refund, source="reconcile")
                applied_refunds += 1
            ledger_credits = _credits(conn)
            provider_ids: set[str] = set()
            for charge in payments.list_charges(since):
                if not charge.id:
                    continue
                provider_ids.add(charge.id)
                if charge.id not in ledger_credits and abs(int(charge.amount_cents)) > tolerance:
                    divergences.append(
                        {
                            "kind": "payment_missing_in_ledger",
                            "external_id": charge.id,
                            "amount_cents": charge.amount_cents,
                        }
                    )
                elif (
                    charge.id in ledger_credits
                    and abs(int(charge.amount_cents) - ledger_credits[charge.id]) > tolerance
                ):
                    divergences.append(
                        {
                            "kind": "payment_amount_mismatch",
                            "external_id": charge.id,
                            "amount_cents": charge.amount_cents,
                            "ledger_cents": ledger_credits[charge.id],
                        }
                    )
            for eid in set(ledger_credits) - provider_ids:
                if eid and ledger_credits.get(eid, 0) > tolerance:
                    divergences.append({"kind": "ledger_credit_absent_at_provider", "external_id": eid})
        except CapabilityDisabled:
            skipped.append("payments")

    checked = [s for s in ("cards", "payments") if s not in skipped]
    if not checked:
        report = {
            "ok": False,
            "divergences": [],
            "skipped": skipped,
            "applied_refunds": 0,
            "reason": "no providers to reconcile",
            "at": utcnow(),
        }
    else:
        report = {
            "ok": len(divergences) == 0,
            "divergences": divergences,
            "skipped": skipped,
            "applied_refunds": applied_refunds,
            "at": utcnow(),
        }

    if paths is not None:
        dest = paths.home / "reconcile-last.json"
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
