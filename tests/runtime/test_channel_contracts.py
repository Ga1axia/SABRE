from __future__ import annotations

from core.config import load_defaults, write_yaml
from core.runtime.tap import handle_hook

QUESTION = "Should we buy example.com?"


def _pre(session: str, channel: str, question: str = QUESTION) -> dict:
    return {
        "hook_event_name": "pre_llm_call",
        "session_id": session,
        "extra": {"user_message": question, "user": "UOP", "channel": channel},
    }


def test_same_question_differs_in_directives_and_requests(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_OPERATOR_ID", "UOP")
    d = handle_hook(_pre("sess-dir", "directives"), sabre_home)
    r = handle_hook(_pre("sess-req", "requests"), sabre_home)
    d_ctx = d.get("context") or ""
    r_ctx = r.get("context") or ""
    assert "24 hours" in d_ctx
    assert "structurally cannot" in r_ctx
    assert d_ctx != r_ctx
    assert QUESTION in d_ctx or "direction" in d_ctx.lower() or "CHANNEL CONTRACT" in d_ctx


def test_directives_contract_has_prd_24h_clause(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_OPERATOR_ID", "UOP")
    out = handle_hook(_pre("sess-24h", "directives"), sabre_home)
    ctx = out.get("context") or ""
    assert "24 hours" in ctx
    assert "recommendation" in ctx.lower()
    assert "permission" in ctx.lower()


def test_channel_id_maps_to_slug(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_OPERATOR_ID", "UOP")
    write_yaml(sabre_home.sabre_yaml, {"channel_ids": {"directives": "CDIR", "requests": "CREQ"}})
    out = handle_hook(
        {
            "hook_event_name": "pre_llm_call",
            "session_id": "sess-cid",
            "extra": {"user_message": QUESTION, "user": "UOP", "channel_id": "CDIR"},
        },
        sabre_home,
    )
    assert "24 hours" in (out.get("context") or "")


def test_every_default_channel_has_a_contract_file():
    from core.paths import core_dir

    names = list(load_defaults().get("channels") or [])
    assert names == [
        "directives",
        "requests",
        "approvals",
        "status",
        "logs",
        "ventures",
        "postmortems",
        "revenue",
    ]
    missing = [n for n in names if not (core_dir() / "channels" / f"{n}.md").exists()]
    assert not missing, missing


def test_speech_act_same_question_is_recognizably_different():
    from core.runtime.channels import render_speech_act

    q = QUESTION
    d = render_speech_act("directives", q)
    r = render_speech_act("requests", q)
    assert d != r
    assert "24 hours" in d
    assert "Recommendation:" in d
    assert "structurally cannot" in r
    assert "Never ask permission" in r
    assert q in d
    assert q in r


def test_cli_without_channel_does_not_inject_a_contract(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_OPERATOR_ID", "UOP")
    out = handle_hook(
        {
            "hook_event_name": "pre_llm_call",
            "session_id": "sess-cli-ch",
            "extra": {"user_message": QUESTION, "user": "UOP"},
        },
        sabre_home,
    )
    assert "CHANNEL CONTRACT" not in (out.get("context") or "")
