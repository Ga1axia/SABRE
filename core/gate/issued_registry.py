"""Gate-owned issued-card registry. Primary evidence for internal spend; not agent-writable."""

from __future__ import annotations

import sqlite3

from core.db import connect
from core.drivers import Charge
from core.paths import Paths


def is_internal_charge(paths: Paths, charge: Charge) -> bool:
    conn = connect(paths.db)
    try:
        return is_internal_charge_conn(conn, charge)
    finally:
        conn.close()


def is_internal_charge_conn(conn: sqlite3.Connection, charge: Charge) -> bool:
    for ref in _refs(charge):
        if _in_registry(conn, ref):
            return True
    return False


def _refs(charge: Charge) -> list[str]:
    refs: list[str] = []
    if charge.card_id:
        refs.append(charge.card_id)
    if charge.payer_ref:
        refs.append(charge.payer_ref)
        if charge.payer_ref.startswith("lithic:"):
            refs.append(charge.payer_ref.split(":", 1)[1])
    return refs


def _in_registry(conn: sqlite3.Connection, ref: str) -> bool:
    if not ref:
        return False
    row = conn.execute(
        "SELECT 1 FROM cards WHERE id=? OR provider_ref=? OR provider_ref=?",
        (ref, ref, f"lithic:{ref}" if not ref.startswith("lithic:") else ref),
    ).fetchone()
    return row is not None
