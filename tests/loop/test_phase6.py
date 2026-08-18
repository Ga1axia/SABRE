from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from core.config import load_settings, write_yaml
from core.db import connect, utcnow
from core.drivers import Charge
from core.drivers.cards.registry import CHARGES, reset
from core.drivers.payments.memory import MemoryPaymentDriver
from core.gate.reconcile import reconcile
from core.gate.server import make_handler
from core.gate.submit import submit_intent
from core.hooks.ingest import ingest_payment
from core.ids import new_id
from core.loop.board import lint_delegation, write_task
from core.loop.scan import scan, score_candidate
from core.loop.tick import tick


def _start_gate(sabre_home):
    settings = load_settings(sabre_home)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
    Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _enable_cards(sabre_home):
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "drivers": {"cards": {"name": "memory", "enabled": True}, "payments": {"name": "memory", "enabled": True}},
            "envelopes": {
                "spend": {
                    "per_transaction_max": 50,
                    "daily_max": 150,
                    "monthly_max": 1200,
                    "per_venture_max": 400,
                    "allowed_categories": ["domains"],
                    "blocked_categories": [],
                },
                "portfolio": {"max_concurrent_ventures": 3},
            },
            "reconcile": {"tolerance_cents": 100},
        },
    )


def test_delegation_lint_requires_acceptance():
    assert lint_delegation({"goal": "do", "acceptance": ""}) == ["acceptance criteria required"]
    assert lint_delegation({"goal": "do", "acceptance": "done"}) == []


def test_write_task_rejects_missing_acceptance(sabre_home):
    with pytest.raises(ValueError, match="acceptance"):
        write_task(sabre_home, {"goal": "ship", "priority": "high"})


def test_main_loop_claims_highest_priority_ready_task(sabre_home, monkeypatch):
    write_task(
        sabre_home,
        {"id": "T-low", "goal": "later", "acceptance": "logged", "priority": "low", "status": "ready"},
    )
    write_task(
        sabre_home,
        {"id": "T-high", "goal": "first", "acceptance": "shipped", "priority": "high", "status": "ready"},
    )
    httpd, url = _start_gate(sabre_home)
    monkeypatch.setenv("SABRE_GATE_URL", url)
    try:
        result = tick(sabre_home)
        assert result.get("ok") is True
        claimed = result.get("claimed") or {}
        assert claimed.get("id") == "T-high"
        conn = connect(sabre_home.db)
        row = conn.execute("SELECT status, claimed_by FROM tasks WHERE id='T-high'").fetchone()
        conn.close()
        assert row["status"] == "in-progress"
        assert row["claimed_by"] == "core"
        again = tick(sabre_home)
        assert (again.get("claimed") or {}).get("id") == "T-low"
    finally:
        httpd.shutdown()


def test_opportunity_scan_weights_skill_reuse(sabre_home):
    dest = sabre_home.work / "opportunities"
    dest.mkdir(parents=True)
    (dest / "a.json").write_text(
        json.dumps(
            {
                "slug": "fresh",
                "ttfd_days": 7,
                "spend_to_first_dollar_cents": 5000,
                "evidence": 0.8,
                "skills": [],
            }
        ),
        encoding="utf-8",
    )
    (dest / "b.json").write_text(
        json.dumps(
            {
                "slug": "reuse",
                "ttfd_days": 14,
                "spend_to_first_dollar_cents": 8000,
                "evidence": 0.5,
                "skills": ["landing-page"],
            }
        ),
        encoding="utf-8",
    )
    out = scan(sabre_home, {"landing-page"})
    slugs = [c["slug"] for c in out["candidates"]]
    assert slugs[0] == "reuse"
    assert score_candidate(out["candidates"][0], {"landing-page"}) >= score_candidate(
        out["candidates"][1], {"landing-page"}
    )


def test_kill_sweep_writes_postmortem(sabre_home, monkeypatch):
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO ventures(id, slug, name, thesis, icp, status, kill_criteria, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            "V-old",
            "stale",
            "Stale",
            "would print money",
            "",
            "building",
            json.dumps({"no_revenue_spend_cents": 15000, "no_revenue_days": 21}),
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()
    httpd, url = _start_gate(sabre_home)
    monkeypatch.setenv("SABRE_GATE_URL", url)
    try:
        r = httpx.post(f"{url}/v1/loop/kill-sweep", json={}, timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert body["killed"]
        assert body["killed"][0]["slug"] == "stale"
        conn = connect(sabre_home.db)
        v = conn.execute("SELECT status, close_reason FROM ventures WHERE id='V-old'").fetchone()
        pm = conn.execute("SELECT believed, happened FROM postmortems WHERE venture_id='V-old'").fetchone()
        conn.close()
        assert v["status"] == "killed"
        assert "21 days" in (v["close_reason"] or "")
        assert pm["believed"] == "would print money"
        assert "21 days" in (pm["happened"] or "")
    finally:
        httpd.shutdown()


def test_skill_promotion_needs_two_nonnegative_ventures(sabre_home, monkeypatch):
    conn = connect(sabre_home.db)
    sid = new_id("SK")
    conn.execute(
        "INSERT INTO skills(id, name, status, uses, net_cents, created_at) VALUES (?,?,?,?,?,?)",
        (sid, "landing-page", "candidate", 0, 0, utcnow()),
    )
    for slug, vid, credit in (("one", "V-a", 500), ("two", "V-b", 800)):
        conn.execute(
            """INSERT INTO ventures(id, slug, name, thesis, status, kill_criteria, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (vid, slug, slug, "t", "earning", "{}", utcnow()),
        )
        conn.execute(
            """INSERT INTO transactions(
                   id, venture_id, direction, amount_cents, currency, category, source, occurred_at
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (new_id("TX"), vid, "credit", credit, "USD", "revenue", "webhook", utcnow()),
        )
    conn.commit()
    conn.close()
    httpd, url = _start_gate(sabre_home)
    try:
        for vid in ("V-a", "V-b"):
            r = httpx.post(f"{url}/v1/skills/{sid}/record-use", json={"venture_id": vid}, timeout=5)
            assert r.status_code == 200
        r = httpx.post(f"{url}/v1/loop/promote", json={}, timeout=5)
        assert r.status_code == 200
        assert sid in r.json()["promoted"]
        conn = connect(sabre_home.db)
        status = conn.execute("SELECT status FROM skills WHERE id=?", (sid,)).fetchone()[0]
        conn.close()
        assert status == "promoted"
    finally:
        httpd.shutdown()


def test_adversarial_review_attaches_dissent_on_red(sabre_home):
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    result = submit_intent(
        settings,
        conn,
        {"kind": "core_change", "payload": {"path": "core/gate/classify.py"}, "rationale": "rewrite policy"},
    )
    conn.commit()
    row = conn.execute("SELECT dissent, classification FROM intents WHERE id=?", (result["id"],)).fetchone()
    conn.close()
    assert result["classification"] == "red"
    assert row["dissent"]
    assert "gpt-4.1-mini" in row["dissent"] or "review" in row["dissent"].lower()


def test_spend_issues_card_and_charges(sabre_home):
    reset()
    _enable_cards(sabre_home)
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO ventures(id, slug, name, thesis, status, kill_criteria, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        ("V-pay", "geo-audit", "Geo", "t", "building", "{}", utcnow()),
    )
    conn.commit()
    result = submit_intent(
        settings,
        conn,
        {
            "kind": "spend",
            "venture": "geo-audit",
            "payload": {"category": "domains", "amount_cents": 100, "vendor": "namecheap"},
            "rationale": "domain",
        },
    )
    conn.commit()
    assert result.get("classification") == "green"
    tx = conn.execute("SELECT card_id, external_id, amount_cents FROM transactions WHERE direction='debit'").fetchone()
    card = conn.execute("SELECT spent_cents FROM cards WHERE id=?", (tx["card_id"],)).fetchone()
    conn.close()
    assert tx["external_id"]
    assert tx["amount_cents"] == 100
    assert card["spent_cents"] == 100
    assert any(c.id == tx["external_id"] for charges in CHARGES.values() for c in charges)


def test_webhook_revenue_ingest_is_not_agent_writable(sabre_home):
    reset()
    pay = MemoryPaymentDriver()
    event = pay.verify_webhook(
        json.dumps(
            {"kind": "charge", "payload": {"amount_cents": 900, "external_id": "ch_rev", "payer_ref": "cus_ext"}}
        ).encode(),
        {},
    )
    assert ingest_payment(sabre_home, pay, event) == "credited"
    conn = connect(sabre_home.db)
    row = conn.execute("SELECT category, source, direction FROM transactions WHERE external_id='ch_rev'").fetchone()
    conn.close()
    assert row["category"] == "revenue"
    assert row["source"] == "webhook"
    assert row["direction"] == "credit"


def test_reconcile_tolerance_band_ignores_sub_dollar_gap(sabre_home):
    reset()
    conn = connect(sabre_home.db)
    pay = MemoryPaymentDriver()
    pay.record_charge(Charge(id="ch_tiny", amount_cents=50, occurred_at=utcnow(), payer_ref="cus"))
    report = reconcile({"cards": None, "payments": pay}, conn, paths=sabre_home)
    assert report["ok"] is True
    assert report["divergences"] == []
    pay.record_charge(Charge(id="ch_big", amount_cents=1200, occurred_at=utcnow(), payer_ref="cus"))
    report = reconcile({"cards": None, "payments": pay}, conn, paths=sabre_home)
    assert report["ok"] is False
    assert any(d.get("external_id") == "ch_big" for d in report["divergences"])
    conn.close()


def test_portfolio_caps_concurrent_ventures(sabre_home, monkeypatch):
    _enable_cards(sabre_home)
    httpd, url = _start_gate(sabre_home)
    try:
        for i in range(3):
            r = httpx.post(
                f"{url}/v1/ledger/ventures",
                json={"slug": f"v{i}", "thesis": "idea"},
                timeout=5,
            )
            assert r.status_code == 200
            assert r.json().get("dissent")
        r = httpx.post(f"{url}/v1/ledger/ventures", json={"slug": "v3", "thesis": "overflow"}, timeout=5)
        assert r.status_code == 409
    finally:
        httpd.shutdown()
