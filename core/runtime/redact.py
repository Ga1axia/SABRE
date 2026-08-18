"""Redact secret shapes and registered proxy token names at write time."""

from __future__ import annotations

import re

from core.paths import Paths
from core.proxy.store import names

PATTERNS = [
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"xapp-[A-Za-z0-9-]+"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
]


def redact(text: str, paths: Paths | None = None) -> str:
    out = text
    for pat in PATTERNS:
        out = pat.sub("[redacted]", out)
    if paths is not None:
        for n in names(paths):
            out = out.replace(n, "[secret]")
    return out
