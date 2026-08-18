"""Thin re-exports so each rule file is independently testable."""

from core.gate.classify import (
    RULES,
    rule_account_registry,
    rule_category,
    rule_ceilings,
    rule_code,
    rule_core_change,
    rule_hosting_missing,
    rule_no_spend,
    rule_provenance,
    rule_publish,
    rule_rate_windows,
    rule_research,
    rule_spend_frozen,
    rule_unknown_kind,
)

__all__ = [
    "RULES",
    "rule_account_registry",
    "rule_category",
    "rule_ceilings",
    "rule_code",
    "rule_core_change",
    "rule_hosting_missing",
    "rule_no_spend",
    "rule_provenance",
    "rule_publish",
    "rule_rate_windows",
    "rule_research",
    "rule_spend_frozen",
    "rule_unknown_kind",
]
