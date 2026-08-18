from __future__ import annotations

from core.config import load_settings
from core.proxy.store import add_secret, get_value, list_secrets
from core.setup.checks import check_iso_secrets


def test_secret_value_not_in_store_file(sabre_home):
    secret = "rk_live_super_secret_value"
    add_secret(sabre_home, "stripe_live", secret, tier=2)
    raw = sabre_home.proxy_store.read_text(encoding="utf-8")
    assert secret not in raw
    assert "ciphertext" in raw
    listed = list_secrets(sabre_home)
    assert listed[0]["name"] == "stripe_live"
    assert secret not in str(listed)
    assert "value" not in listed[0]
    assert get_value(sabre_home, "stripe_live") == secret


def test_isolation_probe_does_not_clobber_master_key(sabre_home):
    add_secret(sabre_home, "keep", "must-survive")
    original = sabre_home.proxy_key.read_bytes()
    check_iso_secrets(sabre_home, load_settings(sabre_home))
    assert sabre_home.proxy_key.read_bytes() == original
    assert get_value(sabre_home, "keep") == "must-survive"
    probe = sabre_home.secrets / ".isolation-probe"
    assert not probe.exists() or probe.read_bytes() != original
