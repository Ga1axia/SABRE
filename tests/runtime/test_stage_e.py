from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread

import yaml

from core.config import load_settings, write_yaml
from core.db import connect
from core.gate.server import make_handler
from core.runtime.hermes import write_hermes_layout
from core.runtime.mcp import handle_message
from core.runtime.submit_context import touch
from core.runtime.tap import handle_hook
from core.runtime.turns import enqueue, expire_stale_turns, find_open


def test_hermes_config_writes_terminal_allowlist_not_yolo(sabre_home):
    layout = write_hermes_layout(sabre_home, load_settings(sabre_home))
    cfg = yaml.safe_load(layout.config_path.read_text(encoding="utf-8"))
    allow = cfg.get("command_allowlist") or []
    assert isinstance(allow, list)
    assert "ls" in allow
    assert "git status" in allow
    assert "pytest *" in allow
    approvals = cfg.get("approvals") or {}
    assert approvals.get("mode") == "manual"
    assert approvals.get("cron_mode") == "deny"
    assert cfg.get("hooks_auto_accept") is True


def test_terminal_denial_alerts_without_blocking_hook(sabre_home, monkeypatch):
    alerts: list[str] = []

    def capture(paths, key, message, channel="status"):
        alerts.append(message)
        return True

    monkeypatch.setattr("core.watch.alert.alert_once", capture)
    handle_hook(
        {
            "hook_event_name": "post_tool_call",
            "session_id": "sess-term",
            "tool_name": "terminal",
            "tool_input": {"command": "rm -rf /"},
            "extra": {"error": "BLOCKED: User denied this potentially dangerous action"},
        },
        sabre_home,
    )
    assert alerts
    assert "not on allowlist" in alerts[0].lower() or "denied" in alerts[0].lower()


def test_stale_other_session_provenance_does_not_amber_spend(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_OPERATOR_ID", "UOP")
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "channel_ids": {"status": "CSTAT"},
            "drivers": {"cards": {"name": "memory", "enabled": True}},
            "envelopes": {
                "spend": {
                    "per_transaction_max": 50,
                    "daily_max": 150,
                    "monthly_max": 1200,
                    "per_venture_max": 400,
                    "allowed_categories": ["domains"],
                    "blocked_categories": [],
                }
            },
        },
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(load_settings(sabre_home)))
    Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("SABRE_GATE_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    try:
        handle_hook(
            {
                "hook_event_name": "pre_llm_call",
                "session_id": "sess-stranger",
                "extra": {"user_message": "buy this domain", "user": "USTRANGER"},
            },
            sabre_home,
        )
        stale = find_open(sabre_home, "sess-stranger")
        assert stale is not None
        enqueue(sabre_home, {"user_message": "operator spend"}, session_id="sess-clean")
        touch(sabre_home, "sess-clean")
        reply = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "submit_intent",
                    "arguments": {
                        "kind": "spend",
                        "payload": {"category": "domains", "amount_cents": 100, "vendor": "namecheap"},
                        "rationale": "clean operator spend",
                    },
                },
            },
            sabre_home,
        )
        body = json.loads(reply["result"]["content"][0]["text"])
        assert body.get("classification") == "green"
    finally:
        httpd.shutdown()


def test_expire_stale_turns_clears_old_provenance(sabre_home):
    turn = enqueue(sabre_home, {"user_message": "old"}, session_id="sess-old")
    turn["status"] = "leased"
    turn["provenance"] = [{"trust": "untrusted", "source": "slack", "sender": "U1"}]
    from core.runtime.turns import _write

    _write(sabre_home, turn)
    n = expire_stale_turns(sabre_home, ttl_seconds=0)
    assert n == 1
    assert find_open(sabre_home, "sess-old") is None
