from __future__ import annotations

import sys

from core.config import is_dev


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    if not sys.stdin.isatty() or is_dev() and os_noninteractive():
        return default or ""
    try:
        raw = input(f"       {prompt}{suffix}: ").strip()
    except EOFError:
        return default or ""
    return raw or (default or "")


def confirm(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = ask(f"{prompt} ({hint})", "y" if default else "n")
    if not raw:
        return default
    return raw.lower() in {"y", "yes"}


def os_noninteractive() -> bool:
    import os

    return os.environ.get("SABRE_NONINTERACTIVE", "").strip() in {"1", "true"} or not sys.stdin.isatty()


def announce(step: int, total: int, name: str) -> None:
    print(f"  [{step}/{total}] {name}")
