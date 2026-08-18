"""Stdio MCP server. The only write tool is submit_intent → I1. The agent never opens the DB."""

from __future__ import annotations

import json
import sys
from typing import Any

from core.envfile import load_env
from core.gate.client import gate_post
from core.paths import Paths, default_home

PROTOCOL = "2024-11-05"

SUBMIT_INTENT = {
    "name": "submit_intent",
    "description": (
        "Submit a consequential action to the SABRE gate. This is the only write path. "
        "You never open the database. Known kinds: research, code, spend, publish, deploy, "
        "outreach, account, core_change."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "payload": {"type": "object"},
            "venture": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["kind"],
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [SUBMIT_INTENT]


def submit_intent_tool(arguments: dict[str, Any], paths: Paths | None = None) -> dict[str, Any]:
    paths = paths or Paths(default_home())
    load_env(paths)
    body = {
        "kind": arguments.get("kind"),
        "payload": arguments.get("payload") if isinstance(arguments.get("payload"), dict) else {},
        "rationale": arguments.get("rationale") or "",
    }
    if arguments.get("venture"):
        body["venture"] = arguments["venture"]
    mechanical = provenance_for_submit(paths)
    supplied = arguments.get("provenance")
    merged: list[dict[str, Any]] = []
    if isinstance(supplied, list):
        merged.extend(p for p in supplied if isinstance(p, dict))
    for item in mechanical:
        if item not in merged:
            merged.append(item)
    if merged:
        body["provenance"] = merged
    return gate_post(paths, "/v1/intents", body)


def provenance_for_submit(paths: Paths) -> list[dict[str, Any]]:
    """Mechanical provenance from open turns. The agent cannot omit this to skip rule_provenance."""
    from core.runtime.turns import list_turns

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for turn in list_turns(paths):
        if turn.get("status") not in {"pending", "leased"}:
            continue
        for item in turn.get("provenance") or []:
            if not isinstance(item, dict):
                continue
            key = json.dumps(item, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def call_tool(name: str, arguments: dict[str, Any], paths: Paths | None = None) -> dict[str, Any]:
    if name != "submit_intent":
        return {"error": f"unknown tool {name}", "isError": True}
    return submit_intent_tool(arguments, paths)


def handle_message(msg: dict[str, Any], paths: Paths | None = None) -> dict[str, Any] | None:
    method = msg.get("method")
    mid = msg.get("id")
    if method is None:
        return None
    if mid is None:
        return None
    if method == "initialize":
        return _ok(
            mid,
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sabre-gate", "version": "0.1.0"},
            },
        )
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": list_tools()})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name") or ""
        raw_args = params.get("arguments") or {}
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except json.JSONDecodeError:
                raw_args = {}
        if not isinstance(raw_args, dict):
            raw_args = {}
        result = call_tool(name, raw_args, paths)
        err = bool(result.get("isError") or result.get("error"))
        return _ok(
            mid,
            {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                "isError": err,
            },
        )
    return {
        "jsonrpc": "2.0",
        "id": mid,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _ok(mid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _read() -> dict[str, Any] | None:
    header = b""
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\n", b"\r\n"):
            break
        if line.lstrip().startswith(b"{"):
            return json.loads(line.decode("utf-8"))
        header += line
    length = 0
    for raw in header.decode("utf-8").splitlines():
        if raw.lower().startswith("content-length:"):
            length = int(raw.split(":", 1)[1].strip())
    if not length:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def _write(msg: dict[str, Any]) -> None:
    data = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
    sys.stdout.buffer.flush()


def serve_stdio() -> None:
    load_env()
    while True:
        msg = _read()
        if msg is None:
            return
        reply = handle_message(msg)
        if reply is not None:
            _write(reply)


def main() -> None:
    serve_stdio()


if __name__ == "__main__":
    main()
