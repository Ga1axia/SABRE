"""Load a driver by entry point. Selected in config, never imported by name in gate."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from core.errors import CapabilityDisabled, SabreError


def load_driver(slot: str, name: str, **kwargs: Any) -> Any:
    eps = entry_points()
    group = f"sabre.drivers.{slot}"
    selected = None
    if hasattr(eps, "select"):
        matches = eps.select(group=group)
    else:  # pragma: no cover
        matches = eps.get(group, [])
    for ep in matches:
        if ep.name == name:
            selected = ep
            break
    if selected is None:
        # Fallback for editable installs that have not registered entry points yet.
        selected = _builtin(slot, name)
    if selected is None:
        raise SabreError(f"no {slot} driver named {name}", remedy="check config/sabre.yaml drivers")
    if callable(selected):
        cls = selected
    else:
        cls = selected.load()
    return cls(**kwargs)


def _builtin(slot: str, name: str):
    mapping = {
        ("inference", "openai_compat"): "core.drivers.inference.openai_compat:OpenAICompatDriver",
        ("messaging", "slack"): "core.drivers.messaging.slack:SlackDriver",
        ("cards", "disabled"): "core.drivers.cards.disabled:DisabledCardDriver",
        ("cards", "memory"): "core.drivers.cards.memory:MemoryCardDriver",
        ("payments", "disabled"): "core.drivers.payments.disabled:DisabledPaymentDriver",
        ("payments", "memory"): "core.drivers.payments.memory:MemoryPaymentDriver",
        ("hosting", "disabled"): "core.drivers.hosting.disabled:DisabledHostingDriver",
    }
    target = mapping.get((slot, name))
    if not target:
        return None
    mod, _, attr = target.partition(":")
    import importlib

    return getattr(importlib.import_module(mod), attr)


def require_enabled(slot: str, enabled: bool) -> None:
    if not enabled:
        raise CapabilityDisabled(slot)
