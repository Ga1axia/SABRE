from __future__ import annotations

from core.config import load_defaults, load_settings
from core.db import connect, init_schema
from core.gate.classify import classify
from core.gate.idempotency import bind_key, canonical_key
from core.gate.ledger import get_intent_by_key, insert_intent
from core.gate.submit import submit_intent


def test_idempotency_returns_same_id(tmp_path):
    db = tmp_path / "sabre.db"
    init_schema(db)
    conn = connect(db)
    intent = {
        "kind": "research",
        "idempotency_key": "research:geo-audit:scan:2026-08-17",
        "payload": {},
        "rationale": "scan",
        "provenance": [],
    }
    result = classify(intent, envelopes=load_defaults()["envelopes"])
    a = insert_intent(conn, intent, result.classification, "executed")
    b = insert_intent(conn, intent, result.classification, "executed")
    conn.commit()
    assert a == b
    row = get_intent_by_key(conn, intent["idempotency_key"])
    assert row["id"] == a
    conn.close()


def test_canonical_key_stable_across_payload_key_order():
    a = {"kind": "spend", "venture": "geo", "payload": {"b": 1, "a": 2}}
    b = {"kind": "spend", "venture": "geo", "payload": {"a": 2, "b": 1}}
    assert canonical_key(a) == canonical_key(b)


def test_mismatched_client_key_is_rejected(sabre_home):
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    body = {
        "kind": "research",
        "venture": "geo-audit",
        "payload": {"query": "scan"},
        "idempotency_key": "fresh-random-key",
        "rationale": "scan",
    }
    result = submit_intent(settings, conn, body)
    conn.commit()
    assert result.get("state") == "refused"
    assert "idempotency_key" in (result.get("error") or "")
    n = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    assert n == 0
    conn.close()


def test_retry_with_omitted_key_collides(sabre_home):
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    body = {
        "kind": "research",
        "venture": "geo-audit",
        "payload": {"query": "scan"},
        "rationale": "scan",
    }
    first = submit_intent(settings, conn, body)
    conn.commit()
    second = submit_intent(settings, conn, dict(body))
    conn.commit()
    assert first["id"] == second["id"]
    assert second.get("replayed") is True
    n = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    assert n == 1
    conn.close()


def test_bind_key_accepts_canonical():
    intent = {"kind": "research", "venture": "v", "payload": {"q": 1}}
    bound = bind_key(intent)
    assert bound["idempotency_key"] == canonical_key(intent)
    again = bind_key(bound)
    assert again["idempotency_key"] == bound["idempotency_key"]
