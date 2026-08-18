"""Local tokens×price table. Providers rarely return dollars; never record a silent zero."""

from __future__ import annotations

# USD per 1M tokens. Used when the provider omits a cost field.
PRICES_PER_MILLION: dict[str, dict[str, float]] = {
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "default": {"input": 2.00, "output": 8.00},
}


def estimate_cost_cents(
    model: str | None,
    tokens_in: int,
    tokens_out: int,
    *,
    provider_cost_cents: int | None = None,
) -> int | None:
    """Return integer cents, or None when there is nothing to attribute.

    Provider dollars win when present and > 0. Tokens that round below 1¢ are None,
    never a silent 0 or an invented 1¢.
    """
    if provider_cost_cents is not None and int(provider_cost_cents) > 0:
        return int(provider_cost_cents)
    tin = int(tokens_in or 0)
    tout = int(tokens_out or 0)
    if tin <= 0 and tout <= 0:
        return None
    key = (model or "").strip() or "default"
    prices = PRICES_PER_MILLION.get(key) or PRICES_PER_MILLION["default"]
    dollars = (tin / 1_000_000) * prices["input"] + (tout / 1_000_000) * prices["output"]
    cents = int(round(dollars * 100))
    if cents < 1:
        return None
    return cents
