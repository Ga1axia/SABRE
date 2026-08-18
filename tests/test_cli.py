from __future__ import annotations

import sys
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


def test_install_sh_is_present():
    root = Path(__file__).resolve().parent.parent
    script = root / "install.sh"
    assert script.is_file()
    # Syntax check only — does not assert on script body text.
    if sys.platform != "win32":
        proc = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
