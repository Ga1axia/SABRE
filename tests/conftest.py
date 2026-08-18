"""Shared test fixtures."""

from __future__ import annotations

import pytest

from core.db import init_schema
from core.paths import Paths
from core.watch.killswitch import install_readonly


@pytest.fixture
def sabre_home(tmp_path, monkeypatch) -> Paths:
    home = tmp_path / "sabre"
    monkeypatch.setenv("SABRE_HOME", str(home))
    monkeypatch.setenv("SABRE_DEV", "1")
    monkeypatch.setenv("SABRE_SKIP_LIVE", "1")
    monkeypatch.setenv("SABRE_NONINTERACTIVE", "1")
    monkeypatch.setenv("SABRE_GATE_INSECURE", "1")
    monkeypatch.setenv("SABRE_INFERENCE_KEY", "sk-test")
    monkeypatch.setenv("SABRE_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SABRE_SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("SABRE_OPERATOR_ID", "UTEST")
    paths = Paths(home)
    paths.ensure()
    init_schema(paths.db)
    install_readonly(paths)
    return paths


@pytest.fixture(autouse=True)
def _reset_net(sabre_home):
    from core.net import reset_for_tests, set_hooks

    reset_for_tests()
    set_hooks(on_open=None, on_close=None)
    yield
    reset_for_tests()
    set_hooks(on_open=None, on_close=None)
