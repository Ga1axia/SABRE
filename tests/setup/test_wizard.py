from __future__ import annotations

from core.setup.steps import STEPS
from core.setup.wizard import run_wizard


def test_eighteen_steps():
    assert len(STEPS) == 18
    assert [s.number for s in STEPS] == list(range(1, 19))


def test_wizard_resume_and_skip(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_SKIP_LIVE", "1")
    rc = run_wizard(sabre_home, interactive=False)
    assert rc == 0
    state = sabre_home.setup_state
    import json

    data = json.loads(state.read_text(encoding="utf-8"))
    assert 10 in data.get("skipped") or 10 in data.get("completed")
    # resume should be a no-op success
    rc2 = run_wizard(sabre_home, resume=True, interactive=False)
    assert rc2 == 0
    # re-run one optional step
    rc3 = run_wizard(sabre_home, step=10, interactive=False)
    assert rc3 == 0


def test_company_md_written(sabre_home, monkeypatch):
    monkeypatch.setenv("SABRE_SKIP_LIVE", "1")
    run_wizard(sabre_home, interactive=False)
    assert (sabre_home.work / "COMPANY.md").exists()
    text = (sabre_home.work / "COMPANY.md").read_text(encoding="utf-8")
    assert "Anti-playbook" in text
