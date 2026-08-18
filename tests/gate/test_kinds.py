from __future__ import annotations

import inspect

from core.gate.classify import KNOWN_KINDS, RULES, rule_unknown_kind


def test_every_known_kind_has_a_rule_that_names_it():
    named: set[str] = set()
    for rule in RULES:
        if rule is rule_unknown_kind:
            continue
        src = inspect.getsource(rule)
        for kind in KNOWN_KINDS:
            if f'"{kind}"' in src or f"'{kind}'" in src:
                named.add(kind)
    missing = KNOWN_KINDS - named
    assert not missing, f"known kinds with no naming rule: {sorted(missing)}"
