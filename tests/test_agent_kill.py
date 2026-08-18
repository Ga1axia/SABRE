from __future__ import annotations

from pathlib import Path

from core.runtime.agent import handle_slash


def test_agent_source_has_no_unkill_file_ops():
    src = Path(__file__).resolve().parents[1] / "core" / "runtime" / "agent.py"
    text = src.read_text(encoding="utf-8")
    assert "import engage" not in text
    assert "import release" not in text
    assert "request_unkill" not in text
    assert ".unlink" not in text
    assert "killswitch.engage" not in text
    assert "killswitch.release" not in text


def test_agent_unkill_slash_refuses(sabre_home):
    msg = handle_slash(sabre_home, "/unkill")
    assert "operator-only" in msg.lower()
    assert not sabre_home.kill_file.exists()
