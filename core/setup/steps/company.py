from __future__ import annotations

import subprocess
from typing import Any

from core.setup.prompt import ask, os_noninteractive

number = 18
name = "Company identity"
optional = False

TEMPLATE = """# Identity

{name} is an agent-operated company. It will: {will}
It will not: {wont}

# Current position

Not yet generated.

# Playbook

(empty)

# Anti-playbook

(empty — load-bearing; do not delete this section)

# Decisions

# Open questions
"""


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {
            "name": "SABRE Company",
            "will": "find and pursue software ventures",
            "wont": "impersonate a specific human, touch operator accounts, or spend past envelopes",
        }
    return {
        "name": ask("Company name", "SABRE Company"),
        "will": ask("What it will do", "find and pursue software ventures"),
        "wont": ask("What it will not do", "impersonate a specific human or touch operator accounts"),
    }


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    work = ctx["paths"].work
    work.mkdir(parents=True, exist_ok=True)
    (work / "board").mkdir(exist_ok=True)
    (work / "ventures").mkdir(exist_ok=True)
    (work / "scratch").mkdir(exist_ok=True)
    path = work / "COMPANY.md"
    path.write_text(
        TEMPLATE.format(
            name=answers.get("name") or "SABRE Company",
            will=answers.get("will") or "find and pursue software ventures",
            wont=answers.get("wont") or "impersonate a specific human",
        ),
        encoding="utf-8",
    )
    if not (work / ".git").exists():
        subprocess.run(["git", "init"], cwd=work, check=False, capture_output=True)
        subprocess.run(["git", "add", "COMPANY.md"], cwd=work, check=False, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "company identity", "--allow-empty"],
            cwd=work,
            check=False,
            capture_output=True,
        )


def verify(ctx: dict[str, Any]) -> str | None:
    if not (ctx["paths"].work / "COMPANY.md").exists():
        return "COMPANY.md missing"
    return None
