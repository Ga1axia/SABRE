from __future__ import annotations

from core.config import load_defaults, load_settings
from core.gate.classify import KNOWN_KINDS, LedgerView, classify


def test_every_known_kind_has_kind_specific_outcome(sabre_home):
    """Behavior probe (C6 inverse): each kind must produce a kind-specific classification."""
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
    assert not missing, f"known kinds without kind-specific outcome: {sorted(missing)}"
