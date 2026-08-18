from __future__ import annotations

import pytest

from core.runtime.browser import resolve_binary
from core.runtime.browser_session import persistence_probe


@pytest.mark.skipif(resolve_binary() is None, reason="no chromium-family browser installed")
def test_browser_profile_persists_across_relaunch(sabre_home):
    result = persistence_probe(sabre_home)
    assert result["cookies_after_reopen"] >= result["cookies_after_first"]
    assert result["operator_cookies_unchanged"] is True
