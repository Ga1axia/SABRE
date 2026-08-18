"""Stage C audit hypotheses: the earlier-audit / Phase-3-unproven claims.

These tests encode the BUG as the expected outcome. They fail if the current
code does not have that bug. They are not product acceptance tests.

Run: python -m pytest tests/gate/stage_c_hypotheses.py -q --tb=line
"""

from __future__ import annotations

from threading import Thread

from core.config import load_defaults, load_settings, write_yaml
from core.db import connect, later, utcnow
from core.gate.classify import KNOWN_KINDS, LedgerView, classify
from core.gate.ledger import claim_task, expire_held_red
from core.gate.submit import submit_intent


def test_c1_earlier_audit_fresh_lease_is_immediately_stealable(sabre_home):
    """C1 earlier audit: lease_until is utcnow(), so B steals immediately."""
    conn = connect(sabre_home.db)
    conn.execute(
        """INSERT INTO tasks(id, goal, acceptance, status, created_at)
           VALUES ('T-c1', 'do', 'done', 'ready', ?)""",
        (utcnow(),),
    )
    conn.commit()
    assert claim_task(conn, "T-c1", "agent-a", lease_seconds=900) is True
    stolen = claim_task(conn, "T-c1", "agent-b", lease_seconds=900)
    conn.close()
    assert stolen is True


def test_c2_earlier_audit_eight_day_old_red_stays_held(sabre_home):
    """C2 earlier audit: red_expire_days is never read, so old reds stay held."""
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    old = later(-8 * 86400)
    conn.execute(
        """INSERT INTO intents(
               id, kind, classification, payload, idempotency_key, rationale,
               state, created_at
           ) VALUES (?,?,?,?,?,?,?,?)""",
        ("I-c2", "spend", "red", "{}", "c2-old", "too much", "held", old),
    )
    conn.commit()
    expire_held_red(conn, settings.red_expire_days)
    conn.commit()
    state = conn.execute("SELECT state FROM intents WHERE id='I-c2'").fetchone()["state"]
    conn.close()
    assert state == "held"


def test_c3_client_supplied_fresh_key_is_accepted(sabre_home):
    """C3 unproven claim inverse: a random client key is stored as-is."""
    settings = load_settings(sabre_home)
    conn = connect(sabre_home.db)
    result = submit_intent(
        settings,
        conn,
        {
            "kind": "research",
            "venture": "geo-audit",
            "payload": {"query": "c3"},
            "idempotency_key": "fresh-random-key",
            "rationale": "scan",
        },
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    conn.close()
    assert result.get("state") != "refused"
    assert n == 1


def test_c4_both_concurrent_spends_are_green(sabre_home):
    """C4 unproven claim inverse: two concurrent greens both pass the ceiling."""
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "drivers": {"cards": {"name": "memory", "enabled": True}},
            "envelopes": {
                "spend": {
                    "per_transaction_max": 50,
                    "daily_max": 1.50,
                    "monthly_max": 1200,
                    "per_venture_max": 400,
                    "allowed_categories": ["domains"],
                    "blocked_categories": [],
                }
            },
        },
    )
    settings = load_settings(sabre_home)
    results: list[dict] = []

    def worker(vendor: str) -> None:
        conn = connect(sabre_home.db)
        try:
            results.append(
                submit_intent(
                    settings,
                    conn,
                    {
                        "kind": "spend",
                        "venture": "geo-audit",
                        "payload": {
                            "category": "domains",
                            "amount_cents": 100,
                            "vendor": vendor,
                            "description": vendor,
                        },
                        "rationale": "domain",
                    },
                )
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            results.append({"error": str(exc), "state": "failed"})
            conn.rollback()
        finally:
            conn.close()

    t1 = Thread(target=worker, args=("namecheap",))
    t2 = Thread(target=worker, args=("porkbun",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    greens = [r for r in results if r.get("classification") == "green" and r.get("state") == "executed"]
    assert len(greens) == 2


def test_c5_gate_stores_agent_supplied_cost(sabre_home):
    """C5 unproven claim inverse: agent cost_cents wins."""
    from http.server import ThreadingHTTPServer
    from threading import Thread as T

    import httpx

    from core.gate.server import make_handler

    settings = load_settings(sabre_home)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
    T(target=httpd.serve_forever, daemon=True).start()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{httpd.server_address[1]}/v1/events",
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
        conn = connect(sabre_home.db)
        stored = conn.execute("SELECT cost_cents FROM events").fetchone()[0]
        conn.close()
    finally:
        httpd.shutdown()
    assert r.json()["cost_cents"] == 999999
    assert stored == 999999


def test_c6_a_known_kind_has_no_kind_specific_outcome():
    """C6 unproven claim inverse: some KNOWN_KINDS has no kind-specific rule outcome."""
    envelopes = load_defaults()["envelopes"]
    probes = {
        "spend": classify(
            {"kind": "spend", "payload": {"category": "not-allowed", "amount_cents": 1}},
            envelopes={**envelopes, "spend": {**envelopes.get("spend", {}), "allowed_categories": ["domains"]}},
            no_spend=False,
        ),
        "publish": classify(
            {"kind": "publish", "payload": {"domain": "evil.example"}},
            envelopes={**envelopes, "publish": {"domains_allowed": ["allowed.example"]}},
        ),
        "deploy": classify({"kind": "deploy", "payload": {}}, envelopes=envelopes, hosting_enabled=False),
        "outreach": classify(
            {"kind": "outreach", "payload": {"action": "email", "account_id": "default"}},
            envelopes=envelopes,
            ledger=LedgerView(rate_counts={("default", "email"): 99}),
        ),
        "account": classify(
            {"kind": "account", "payload": {"platform": "brand-new-platform"}},
            envelopes=envelopes,
        ),
        "core_change": classify({"kind": "core_change", "payload": {}}, envelopes=envelopes),
        "research": classify({"kind": "research", "payload": {}}, envelopes=envelopes, no_spend=False),
        "code": classify({"kind": "code", "payload": {"target": "core"}}, envelopes=envelopes),
    }
    hits = {
        "spend": probes["spend"].classification == "red",
        "publish": probes["publish"].classification == "red",
        "deploy": probes["deploy"].classification == "red",
        "outreach": probes["outreach"].classification == "red",
        "account": probes["account"].classification == "amber",
        "core_change": probes["core_change"].classification == "red",
        "research": probes["research"].classification == "green",
        "code": probes["code"].classification == "red",
    }
    missing = {k for k in KNOWN_KINDS if not hits.get(k)}
    assert missing, f"every known kind has a kind-specific outcome: {hits}"
