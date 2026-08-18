from __future__ import annotations

from typing import Any

from core.config import write_yaml
from core.envelopes import derive_envelopes
from core.gate.classify import classify
from core.setup.prompt import ask, os_noninteractive

number = 9
name = "Envelopes"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"monthly": 600.0}
    raw = ask("What monthly amount are you willing to lose entirely? (USD)", "600")
    try:
        monthly = float(raw.replace("$", "").replace(",", "") or "600")
    except ValueError:
        monthly = 600.0
    env = derive_envelopes(monthly, ctx["defaults"])
    spend = env["spend"]
    print(
        f"       → per-transaction ${spend['per_transaction_max']} · "
        f"daily ${spend['daily_max']} · per-venture ${spend['per_venture_max']} · "
        f"monthly ${spend['monthly_max']}"
    )
    return {"monthly": monthly}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    env = derive_envelopes(float(answers.get("monthly") or 600), ctx["defaults"])
    write_yaml(ctx["paths"].envelopes_yaml, {"envelopes": env})


def verify(ctx: dict[str, Any]) -> str | None:
    from core.config import load_settings

    settings = load_settings(ctx["paths"])
    over = {
        "kind": "spend",
        "idempotency_key": "doctor:over-ceiling",
        "payload": {
            "category": "domains",
            "amount_cents": int(settings.envelopes.get("spend", {}).get("per_transaction_max", 50) * 100) + 1,
        },
        "rationale": "synthetic",
        "provenance": [],
    }
    result = classify(over, envelopes=settings.envelopes, no_spend=False)
    if result.classification != "red":
        return "over-ceiling intent was not refused"
    return None
