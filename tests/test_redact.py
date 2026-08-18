from __future__ import annotations

from core.proxy.store import add_secret
from core.runtime.redact import redact


def test_redact_secret_shapes():
    assert "[redacted]" in redact("token xoxb-1234567890-abcdef")
    assert "[redacted]" in redact("key sk-abcdefghijklmnop")
    assert "[redacted]" in redact("ghp_" + "a" * 24)


def test_redact_registered_names(sabre_home):
    add_secret(sabre_home, "stripe_live", "rk_live_not_the_point")
    out = redact("using stripe_live now", sabre_home)
    assert "[secret]" in out
    assert "stripe_live" not in out
