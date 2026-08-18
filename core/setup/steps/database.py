from __future__ import annotations

from typing import Any

from core.db import current_migration, init_schema, migration_head

number = 3
name = "Database"
optional = False


def prompt(_ctx: dict[str, Any]) -> dict[str, Any]:
    return {}


def apply(ctx: dict[str, Any], _answers: dict[str, Any]) -> None:
    init_schema(ctx["paths"].db)


def verify(ctx: dict[str, Any]) -> str | None:
    head = migration_head()
    cur = current_migration(ctx["paths"].db)
    if cur != head:
        return f"schema at {cur}, expected {head}"
    return None
