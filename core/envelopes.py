"""Envelope derivation from a single monthly loss-tolerance number."""

from __future__ import annotations

from typing import Any


def derive_envelopes(monthly_loss: float, defaults: dict[str, Any]) -> dict[str, Any]:
    monthly = max(float(monthly_loss), 1.0)
    spend = {
        "per_transaction_max": round(monthly / 24, 2),
        "daily_max": round(monthly / 8, 2),
        "monthly_max": round(monthly, 2),
        "per_venture_max": round(monthly / 3, 2),
        "allowed_categories": list(
            (defaults.get("envelopes") or {}).get("spend", {}).get(
                "allowed_categories",
                ["hosting", "domains", "saas", "ads", "api_credits", "contractor_micro"],
            )
        ),
        "blocked_categories": list(
            (defaults.get("envelopes") or {}).get("spend", {}).get(
                "blocked_categories",
                ["equity", "legal_retainer", "crypto", "gambling", "prepaid_cards", "payroll"],
            )
        ),
    }
    envelopes = dict(defaults.get("envelopes") or {})
    envelopes["spend"] = spend
    inf = dict(envelopes.get("inference") or {})
    inf["daily_usd"] = round(monthly / 48, 2)
    inf["per_venture_usd"] = round(monthly / 10, 2)
    envelopes["inference"] = inf
    return envelopes
