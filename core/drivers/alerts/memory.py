"""In-memory alert sink for tests. Does not use core.net or Slack circuits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryAlertDriver:
    name = "memory"

    def __init__(self, path: str | Path | None = None, **_: Any):
        self.path = Path(path) if path else Path("alert-fallback.jsonl")

    def send(self, to: str, subject: str, body: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"to": to, "subject": subject, "body": body}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
