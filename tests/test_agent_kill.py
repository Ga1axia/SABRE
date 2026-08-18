from __future__ import annotations

import subprocess
import sys

import pytest

from core.runtime.agent import handle_slash


def test_agent_unkill_slash_refuses(sabre_home):
    msg = handle_slash(sabre_home, "/unkill")
    assert "operator-only" in msg.lower()
    assert not sabre_home.kill_file.exists()
