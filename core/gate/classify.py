"""Policy engine. Pure functions of intent + ledger. Unknown kinds resolve to Red."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["allow", "escalate", "deny"]
Klass = Literal["green", "amber", "red"]

KNOWN_KINDS = {
    "spend",
    "publish",
    "deploy",
    "outreach",
    "account",
    "core_change",
    "research",
    "code",
}

GREEN_KINDS = {"research", "code"}


@dataclass
class LedgerView:
    """Subset of ledger the classifier may read. No network."""

    spend_today_cents: int = 0
    spend_month_cents: int = 0
    spend_venture_cents: int = 0
    rate_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    account_ids: set[str] = field(default_factory=set)
    known_platforms: set[str] = field(default_factory=set)
    spend_frozen: bool = False


@dataclass
class RuleResult:
    decision: Decision
    reason: str
    klass: Klass | None = None


@dataclass
class Classification:
    classification: Klass
    state_hint: str
    reasons: list[str]


def _cents(dollars: float) -> int:
    return int(round(float(dollars) * 100))


def rule_unknown_kind(intent: dict[str, Any], **_: Any) -> RuleResult:
    kind = str(intent.get("kind") or "")
    if kind not in KNOWN_KINDS:
        return RuleResult("deny", f"unknown kind {kind!r}", "red")
    return RuleResult("allow", "known kind")


def rule_no_spend(intent: dict[str, Any], *, no_spend: bool, **_: Any) -> RuleResult:
    if no_spend and intent.get("kind") == "spend":
        return RuleResult("deny", "no-spend mode; sabre setup --step 10", "red")
    return RuleResult("allow", "spend capability")


def rule_core_change(intent: dict[str, Any], **_: Any) -> RuleResult:
    if intent.get("kind") == "core_change":
        return RuleResult("deny", "core_change is Red by construction", "red")
    return RuleResult("allow", "not a core change")


def rule_account_registry(intent: dict[str, Any], *, ledger: LedgerView, **_: Any) -> RuleResult:
    if intent.get("kind") != "account":
        payload = intent.get("payload") or {}
        account_id = payload.get("account_id")
        if account_id and account_id not in ledger.account_ids:
            return RuleResult("deny", f"account {account_id} absent from registry", "red")
        return RuleResult("allow", "account ok or not required")
    payload = intent.get("payload") or {}
    platform = str(payload.get("platform") or "")
    if platform and platform not in ledger.known_platforms:
        return RuleResult("escalate", "first account on a new platform", "amber")
    return RuleResult("allow", "account creation")


def rule_category(intent: dict[str, Any], *, envelopes: dict[str, Any], **_: Any) -> RuleResult:
    if intent.get("kind") != "spend":
        return RuleResult("allow", "not spend")
    spend = (envelopes.get("spend") or {}) if envelopes else {}
    cat = str((intent.get("payload") or {}).get("category") or "")
    blocked = set(spend.get("blocked_categories") or [])
    allowed = set(spend.get("allowed_categories") or [])
    if cat in blocked:
        return RuleResult("deny", f"blocked category {cat}", "red")
    if allowed and cat and cat not in allowed:
        return RuleResult("deny", f"category {cat} not in allowed list", "red")
    return RuleResult("allow", "category ok")


def rule_ceilings(intent: dict[str, Any], *, envelopes: dict[str, Any], ledger: LedgerView, **_: Any) -> RuleResult:
    if intent.get("kind") != "spend":
        return RuleResult("allow", "not spend")
    spend = envelopes.get("spend") or {}
    amount = int((intent.get("payload") or {}).get("amount_cents") or 0)
    per_tx = _cents(spend.get("per_transaction_max") or 0)
    daily = _cents(spend.get("daily_max") or 0)
    monthly = _cents(spend.get("monthly_max") or 0)
    per_v = _cents(spend.get("per_venture_max") or 0)
    if per_tx and amount > per_tx:
        return RuleResult("deny", "exceeds per-transaction ceiling", "red")
    if daily and ledger.spend_today_cents + amount > daily:
        return RuleResult("deny", "exceeds daily ceiling", "red")
    if monthly and ledger.spend_month_cents + amount > monthly:
        return RuleResult("deny", "exceeds monthly ceiling", "red")
    if per_v and ledger.spend_venture_cents + amount > per_v:
        return RuleResult("deny", "exceeds per-venture ceiling", "red")
    if per_tx and amount > 0.5 * per_tx:
        return RuleResult("escalate", "spend above 50% of per-transaction ceiling", "amber")
    return RuleResult("allow", "within ceilings")


def rule_rate_windows(intent: dict[str, Any], *, envelopes: dict[str, Any], ledger: LedgerView, **_: Any) -> RuleResult:
    if intent.get("kind") != "outreach":
        return RuleResult("allow", "not outreach")
    outreach = envelopes.get("outreach") or {}
    payload = intent.get("payload") or {}
    action = str(payload.get("action") or "email")
    key = (str(payload.get("account_id") or "default"), action)
    count = ledger.rate_counts.get(key, 0)
    if action == "email" and count >= int(outreach.get("email_per_day") or 40):
        return RuleResult("deny", "email daily rate exceeded", "red")
    if action.startswith("dm") and count >= int(outreach.get("dm_per_platform_per_day") or 15):
        return RuleResult("deny", "dm daily rate exceeded", "red")
    return RuleResult("allow", "rate ok")


def rule_provenance(intent: dict[str, Any], **_: Any) -> RuleResult:
    provenance = intent.get("provenance") or []
    untrusted = any(isinstance(p, dict) and p.get("trust") == "untrusted" for p in provenance)
    kind = intent.get("kind")
    if untrusted and kind in {"spend", "account", "outreach"}:
        return RuleResult("escalate", "untrusted provenance on money/identity effect", "amber")
    return RuleResult("allow", "provenance ok")


def rule_research(intent: dict[str, Any], **_: Any) -> RuleResult:
    if intent.get("kind") != "research":
        return RuleResult("allow", "not research")
    return RuleResult("allow", "research is an in-envelope green kind")


def rule_code(intent: dict[str, Any], **_: Any) -> RuleResult:
    if intent.get("kind") != "code":
        return RuleResult("allow", "not code")
    target = str((intent.get("payload") or {}).get("target") or "venture")
    if target == "core":
        return RuleResult("deny", "core repo is proposal_only", "red")
    return RuleResult("allow", "venture code is an in-envelope green kind")


def rule_publish(intent: dict[str, Any], *, envelopes: dict[str, Any], **_: Any) -> RuleResult:
    if intent.get("kind") != "publish":
        return RuleResult("allow", "not publish")
    allowed = set((envelopes.get("publish") or {}).get("domains_allowed") or [])
    domain = str((intent.get("payload") or {}).get("domain") or "")
    if allowed and domain and domain not in allowed:
        return RuleResult("deny", f"domain {domain} not in publish allow-list", "red")
    if domain and not allowed:
        return RuleResult("escalate", "publish domain not pre-allowed", "amber")
    return RuleResult("allow", "publish ok")


def rule_spend_frozen(intent: dict[str, Any], *, ledger: LedgerView, **_: Any) -> RuleResult:
    if intent.get("kind") != "spend":
        return RuleResult("allow", "not spend")
    if ledger.spend_frozen:
        return RuleResult("deny", "spend frozen until reconciliation divergences are cleared", "red")
    return RuleResult("allow", "spend not frozen")


def rule_hosting_missing(intent: dict[str, Any], *, hosting_enabled: bool, **_: Any) -> RuleResult:
    if intent.get("kind") == "deploy" and not hosting_enabled:
        return RuleResult("deny", "hosting driver disabled", "red")
    return RuleResult("allow", "hosting ok")


RULES = [
    rule_unknown_kind,
    rule_no_spend,
    rule_core_change,
    rule_account_registry,
    rule_category,
    rule_ceilings,
    rule_rate_windows,
    rule_provenance,
    rule_research,
    rule_code,
    rule_publish,
    rule_spend_frozen,
    rule_hosting_missing,
]


def classify(
    intent: dict[str, Any],
    *,
    envelopes: dict[str, Any],
    ledger: LedgerView | None = None,
    no_spend: bool = True,
    hosting_enabled: bool = False,
) -> Classification:
    ledger = ledger or LedgerView()
    reasons: list[str] = []
    klass: Klass = "green"
    if intent.get("kind") not in KNOWN_KINDS:
        klass = "red"
    ctx = {
        "envelopes": envelopes,
        "ledger": ledger,
        "no_spend": no_spend,
        "hosting_enabled": hosting_enabled,
    }
    for rule in RULES:
        result = rule(intent, **ctx)
        reasons.append(f"{rule.__name__}: {result.reason}")
        if result.decision == "deny":
            return Classification("red", "held", reasons)
        if result.decision == "escalate":
            klass = "amber"
    if klass == "green":
        return Classification("green", "execute", reasons)
    return Classification("amber", "held", reasons)
