from __future__ import annotations

from core.config import load_defaults
from core.envelopes import derive_envelopes
from core.gate.classify import LedgerView, classify


def test_unknown_kind_is_red():
    r = classify({"kind": "teleport", "payload": {}}, envelopes=load_defaults()["envelopes"])
    assert r.classification == "red"


def test_no_spend_spend_is_red():
    r = classify(
        {
            "kind": "spend",
            "payload": {"category": "domains", "amount_cents": 100},
            "rationale": "x",
        },
        envelopes=load_defaults()["envelopes"],
        no_spend=True,
    )
    assert r.classification == "red"


def test_research_is_green():
    r = classify(
        {"kind": "research", "payload": {}, "rationale": "look around"},
        envelopes=load_defaults()["envelopes"],
        no_spend=True,
    )
    assert r.classification == "green"


def test_over_ceiling_refused():
    env = derive_envelopes(600, load_defaults())
    r = classify(
        {
            "kind": "spend",
            "payload": {"category": "domains", "amount_cents": 10_000_00},
            "rationale": "too much",
        },
        envelopes=env,
        no_spend=False,
    )
    assert r.classification == "red"


def test_under_ceiling_green_when_spend_enabled():
    env = derive_envelopes(600, load_defaults())
    r = classify(
        {
            "kind": "spend",
            "payload": {"category": "domains", "amount_cents": 500},
            "rationale": "cheap domain",
            "provenance": [],
        },
        envelopes=env,
        no_spend=False,
        ledger=LedgerView(),
    )
    assert r.classification == "green"


def test_untrusted_provenance_escalates_spend():
    env = derive_envelopes(600, load_defaults())
    r = classify(
        {
            "kind": "spend",
            "payload": {"category": "domains", "amount_cents": 500},
            "rationale": "from a webpage",
            "provenance": [{"source": "web_fetch", "host": "evil.example", "trust": "untrusted"}],
        },
        envelopes=env,
        no_spend=False,
    )
    assert r.classification == "amber"


def test_core_change_is_red():
    r = classify(
        {"kind": "core_change", "payload": {"path": "core/gate/classify.py"}},
        envelopes=load_defaults()["envelopes"],
        no_spend=True,
    )
    assert r.classification == "red"


def test_blocked_category():
    env = derive_envelopes(600, load_defaults())
    r = classify(
        {
            "kind": "spend",
            "payload": {"category": "crypto", "amount_cents": 100},
            "rationale": "nope",
        },
        envelopes=env,
        no_spend=False,
    )
    assert r.classification == "red"


def test_monthly_derivation():
    env = derive_envelopes(600, load_defaults())
    assert env["spend"]["per_transaction_max"] == 25
    assert env["spend"]["daily_max"] == 75
    assert env["spend"]["per_venture_max"] == 200
    assert env["spend"]["monthly_max"] == 600
