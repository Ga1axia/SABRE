from __future__ import annotations

import json
import subprocess
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import yaml

from core.config import load_settings
from core.db import connect
from core.gate.server import make_handler
from core.runtime.agent import handle_slash
from core.runtime.hermes import write_hermes_layout
from core.runtime.mcp import handle_message, list_tools
from core.runtime.tap import handle_hook


def _start_gate(sabre_home):
    settings = load_settings(sabre_home)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(settings))
    Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    return httpd, f"http://127.0.0.1:{port}"


def test_agent_source_has_no_chat_completions_loop():
    src = Path(__file__).resolve().parents[2] / "core" / "runtime" / "agent.py"
    text = src.read_text(encoding="utf-8")
    assert "OpenAICompatDriver" not in text
    assert "complete_turn" not in text
    assert "slack_bolt" not in text
    assert "SocketModeHandler" not in text
    assert "chat/completions" not in text
    assert "gateway" in text
    assert "hermes" in text.lower()


def test_hermes_config_has_prd_runtime_discipline(sabre_home):
    layout = write_hermes_layout(sabre_home, load_settings(sabre_home))
    cfg = yaml.safe_load(layout.config_path.read_text(encoding="utf-8"))
    assert cfg["delegation"]["max_concurrent_children"] == 2
    assert cfg["delegation"]["max_iterations"] == 40
    caps = cfg["tool_loop_guardrails"]["loop_caps"]
    assert caps["max_web_searches"] == 15
    assert caps["max_subagents"] == 8
    comp = cfg["compression"]
    assert comp["enabled"] is True
    assert comp["threshold"] == 0.5
    assert comp["target_ratio"] == 0.2
    assert comp["protect_last_n"] == 20
    assert "sabre-gate" in cfg["mcp_servers"]
    mcp = cfg["mcp_servers"]["sabre-gate"]
    assert mcp["args"] == ["-m", "core.runtime.mcp"]
    hooks = cfg["hooks"]["post_tool_call"]
    assert hooks
    assert "core.runtime.hook" in hooks[0]["command"]
    assert cfg["browser"]["user_data_dir"] == str(sabre_home.browser_profile)
    names = {j["name"] for j in cfg["cron"]}
    assert names >= {"main-loop", "opportunity-scan", "kill-sweep", "reconcile", "promote"}
    soul = layout.soul_path.read_text(encoding="utf-8")
    assert "submit_intent" in soul
    assert "never open the database" in soul.lower()
    assert "browser profile" in soul.lower()


def test_mcp_only_write_tool_is_submit_intent():
    names = {t["name"] for t in list_tools()}
    assert names == {"submit_intent"}
    listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    listed_names = {t["name"] for t in listed["result"]["tools"]}
    assert listed_names == {"submit_intent"}
    unknown = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "write_db", "arguments": {}},
        }
    )
    assert unknown["result"]["isError"] is True


def test_phase1_session_shell_intent_and_tap(sabre_home, monkeypatch):
    httpd, url = _start_gate(sabre_home)
    monkeypatch.setenv("SABRE_GATE_URL", url)
    try:
        shell = subprocess.run(
            [sys.executable, "-c", "print('sabre-shell-ok')"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "sabre-shell-ok" in shell.stdout
        handle_hook(
            {
                "hook_event_name": "post_tool_call",
                "tool_name": "terminal",
                "tool_input": {"command": "python -c \"print('sabre-shell-ok')\""},
                "session_id": "sess-phase1",
                "extra": {"duration_ms": 12, "result": shell.stdout},
            },
            sabre_home,
        )
        reply = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "submit_intent",
                    "arguments": {
                        "kind": "research",
                        "payload": {"query": "phase1 acceptance"},
                        "rationale": "prove gate classify path",
                    },
                },
            },
            sabre_home,
        )
        body = json.loads(reply["result"]["content"][0]["text"])
        assert reply["result"]["isError"] is False
        assert body.get("classification") == "green"
        assert body.get("state") in {"executed", "proposed"}
        handle_hook(
            {
                "hook_event_name": "post_tool_call",
                "tool_name": "submit_intent",
                "tool_input": {"kind": "research", "payload": {"query": "phase1 acceptance"}},
                "session_id": "sess-phase1",
                "extra": {"duration_ms": 5, "result": body},
            },
            sabre_home,
        )
        conn = connect(sabre_home.db)
        events = [dict(r) for r in conn.execute("SELECT tool, args, status, session_id FROM events ORDER BY id")]
        intent = conn.execute("SELECT kind, classification, state FROM intents").fetchone()
        conn.close()
        tools = [e["tool"] for e in events]
        assert "terminal" in tools
        assert "submit_intent" in tools
        assert intent["kind"] == "research"
        assert intent["classification"] == "green"
        log_path = sabre_home.logs / "logs-channel.jsonl"
        assert log_path.exists()
        log_lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(row.get("tool") == "terminal" for row in log_lines)
    finally:
        httpd.shutdown()


def test_unkill_slash_still_operator_only(sabre_home):
    msg = handle_slash(sabre_home, "/unkill")
    assert "operator-only" in msg.lower()
    assert not sabre_home.kill_file.exists()
