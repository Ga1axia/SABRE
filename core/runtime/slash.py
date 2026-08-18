"""Operator-facing slash verbs. Hermes owns Slack; these stay callable for tests and skills."""

from __future__ import annotations

import json

from core.gate.client import gate_get
from core.paths import Paths


def handle_slash(paths: Paths, command: str) -> str:
    if command in {"/kill"}:
        from core.watch.client import request_kill

        try:
            request_kill()
        except RuntimeError as exc:
            return f"Kill request failed: {exc}"
        return "Kill switch requested."
    if command in {"/unkill"}:
        return "Unkill is operator-only. Use sabre unkill on the host."
    if command in {"/status"}:
        env = gate_get(paths, "/v1/ledger/envelopes")
        return json.dumps(env)[:1500]
    return "unknown command"
