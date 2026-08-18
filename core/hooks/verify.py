"""Per-provider webhook signature verification."""

from __future__ import annotations

from collections.abc import Mapping

from core.drivers import Event
from core.errors import CapabilityDisabled


def verify(driver, body: bytes, headers: Mapping[str, str]) -> Event | None:
    if driver is None:
        raise CapabilityDisabled("payments")
    return driver.verify_webhook(body, headers)
