from __future__ import annotations

from core.setup.checks import check_sleep


def test_sleep_check_skips_on_linux(monkeypatch):
    monkeypatch.setattr("core.setup.checks.sys.platform", "linux")
    ok, msg = check_sleep(None, None)  # type: ignore[arg-type]
    assert ok == "skip"
    assert "macos" in msg.lower()


def test_sleep_check_parses_pmset_custom_on_darwin(monkeypatch):
    monkeypatch.setattr("core.setup.checks.sys.platform", "darwin")

    class Proc:
        returncode = 0
        stdout = (
            "AC Power:\n"
            " Sleep On Power Button 1\n"
            " sleep                0\n"
            " disksleep            0\n"
            " displaysleep         0\n"
            " disablesleep         1\n"
            "Battery Power:\n"
            " sleep                1\n"
        )

    monkeypatch.setattr("core.setup.checks.subprocess.run", lambda *a, **k: Proc())
    ok, msg = check_sleep(None, None)  # type: ignore[arg-type]
    assert ok is True
    assert "disablesleep=1" in msg


def test_sleep_check_fails_when_sleep_enabled_on_ac(monkeypatch):
    monkeypatch.setattr("core.setup.checks.sys.platform", "darwin")

    class Proc:
        returncode = 0
        stdout = "AC Power:\n sleep 1\n disablesleep 0\nBattery Power:\n"

    monkeypatch.setattr("core.setup.checks.subprocess.run", lambda *a, **k: Proc())
    ok, msg = check_sleep(None, None)  # type: ignore[arg-type]
    assert ok is False
