from __future__ import annotations

from pathlib import Path

from core.cli.app import build_parser


def test_cli_help():
    parser = build_parser()
    names = None
    for action in parser._actions:
        if getattr(action, "choices", None) and isinstance(action.choices, dict):
            names = set(action.choices)
            break
    assert names is not None
    for verb in (
        "setup",
        "doctor",
        "chat",
        "up",
        "down",
        "status",
        "kill",
        "unkill",
        "logs",
        "envelope",
        "accounts",
        "secrets",
        "venture",
        "personas",
        "backup",
        "restore",
        "upgrade",
    ):
        assert verb in names


def test_install_sh_exists():
    root = Path(__file__).resolve().parent.parent
    text = (root / "install.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    assert "does not create OS users" in text.lower() or "Does not create OS users" in text
    assert "sabre setup" in text
    assert "Windows" in text
    assert "install_hermes" in text
