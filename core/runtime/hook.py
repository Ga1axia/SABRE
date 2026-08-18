"""Hermes post_tool_call stdin hook. Exit 0 and print {} so a logger failure cannot stall the agent."""

from __future__ import annotations

import json
import sys
from typing import Any

from core.envfile import load_env
from core.paths import Paths, default_home
from core.runtime.tap import handle_hook


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    paths = Paths(default_home())
    load_env(paths)
    out: dict[str, Any] = {}
    try:
        result = handle_hook(payload if isinstance(payload, dict) else {}, paths)
        if isinstance(result, dict):
            out = result
    except Exception:
        out = {}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
