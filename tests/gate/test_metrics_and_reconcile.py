from __future__ import annotations

from http.server import ThreadingHTTPServer
from threading import Thread

import httpx

from core.config import load_settings
from core.db import connect, utcnow
from core.drivers import Charge, Refund
from core.drivers.payments.memory import MemoryPaymentDriver
from core.gate.reconcile import reconcile
from core.gate.server import make_handler
from core.ids import new_id


def test_gate_ignores_agent_supplied_cost(sabre_home):
    settings = load_settings(sabre_home)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
    Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        r = httpx.post(
            f"http://127.0.0.1:{port}/v1/events",
            json={
                "actor": "core",
                "tool": "complete",
                "tokens_in": 1_000_000,
                "tokens_out": 0,
                "model": "gpt-4.1-mini",
                "cost_cents": 999999,
            },
            timeout=5,
        )
        assert r.status_code == 200
        assert r.json()["cost_cents"] == 40
        conn = connect(sabre_home.db)
        stored = conn.execute("SELECT cost_cents FROM events").fetchone()[0]
        conn.close()
        assert stored == 40
    finally:
        httpd.shutdown()


def test_gate_ignores_agent_supplied_skill_net(sabre_home):
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    sid = new_id("SK")
    conn.execute(
        """INSERT INTO skills(id, name, status, uses, net_cents, created_at)
           VALUES (?,?,?,?,?,?)""",
        (sid, "scrape", "active", 0, 0, utcnow()),
    )
    conn.commit()
    conn.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
    Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        r = httpx.post(
            f"http://127.0.0.1:{port}/v1/skills/{sid}/record-use",
            json={"net_cents": 50000, "tokens_in": 1_000_000, "tokens_out": 0, "model": "gpt-4.1-mini"},
            timeout=5,
        )
        assert r.status_code == 200
        conn = connect(sabre_home.db)
        row = conn.execute("SELECT uses, net_cents FROM skills WHERE id=?", (sid,)).fetchone()
        conn.close()
        assert row["uses"] == 1
        assert row["net_cents"] == -40
    finally:
        httpd.shutdown()


def test_reconcile_applies_refunds(sabre_home):
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO transactions(
               id, direction, amount_cents, currency, category, source, external_id, occurred_at
           ) VALUES (?,?,?,?,?,?,?,?)""",
        ("TX-orig", "debit", 500, "USD", "domains", "gate", "ch_1", utcnow()),
    )
    conn.commit()
    pay = MemoryPaymentDriver()
    pay.record_refund(Refund(id="re_1", charge_id="ch_1", amount_cents=500, occurred_at=utcnow()))
    report = reconcile({"cards": None, "payments": pay}, conn, paths=sabre_home)
    conn.commit()
    assert report["applied_refunds"] == 1
    row = conn.execute("SELECT reversed_by FROM transactions WHERE id='TX-orig'").fetchone()
    assert row["reversed_by"]
    credit = conn.execute(
        "SELECT amount_cents, category FROM transactions WHERE category='refund'"
    ).fetchone()
    assert credit["amount_cents"] == 500
    conn.close()


def test_reconcile_flags_missing_provider_charge(sabre_home):
    conn = connect(sabre_home.db)
    pay = MemoryPaymentDriver()
    pay.record_charge(Charge(id="ch_missing", amount_cents=1200, occurred_at=utcnow(), payer_ref="cus"))
    report = reconcile({"cards": None, "payments": pay}, conn, paths=sabre_home)
    assert report["ok"] is False
    assert report["divergences"]
    conn.close()
