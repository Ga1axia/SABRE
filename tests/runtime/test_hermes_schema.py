"""Stage A: SABRE may only write Hermes-recognised config keys. Behavior, not source."""

from __future__ import annotations

import yaml

from core.config import load_settings
from core.runtime.channels import resolve_slug
from core.runtime.hermes import hermes_home, write_hermes_layout
from core.runtime.hermes_schema import unknown_written_keys
from core.setup.checks import check_hermes_schema


def test_written_hermes_config_has_only_recognised_keys(sabre_home):
    layout = write_hermes_layout(sabre_home, load_settings(sabre_home))
    cfg = yaml.safe_load(layout.config_path.read_text(encoding="utf-8"))
    assert unknown_written_keys(cfg) == []


def test_doctor_fails_on_bogus_hermes_key_then_passes(sabre_home):
    write_hermes_layout(sabre_home, load_settings(sabre_home))
    path = hermes_home(sabre_home) / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["not_a_hermes_key"] = True
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    ok, msg = check_hermes_schema(sabre_home, load_settings(sabre_home))
    assert ok is False
    assert "not_a_hermes_key" in msg

    write_hermes_layout(sabre_home, load_settings(sabre_home))
    ok, msg = check_hermes_schema(sabre_home, load_settings(sabre_home))
    assert ok is True, msg


def test_doctor_fails_on_spoofed_hermes_version_then_passes(sabre_home, monkeypatch):
    from core.setup.checks import check_hermes_version

    monkeypatch.setattr("core.runtime.hermes_schema.installed_hermes_version", lambda: "9.9.9")
    ok, msg = check_hermes_version(sabre_home, load_settings(sabre_home))
    assert ok is False
    assert "9.9.9" in msg
    assert "schema audit" in msg.lower()

    monkeypatch.setattr("core.runtime.hermes_schema.installed_hermes_version", lambda: "0.20.1")
    ok, msg = check_hermes_version(sabre_home, load_settings(sabre_home))
    assert ok is True, msg


def test_hermes_pre_llm_payload_has_no_slack_channel(sabre_home):
    extra = {
        "user_message": "Should we buy example.com?",
        "is_first_turn": True,
        "model": "gpt-4.1",
        "platform": "slack",
        "sender_id": "UTEST",
    }
    payload = {"hook_event_name": "pre_llm_call", "session_id": "sess-slack", "extra": extra}
    assert resolve_slug(sabre_home, payload, extra) == ""

