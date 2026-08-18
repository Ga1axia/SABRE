"""#approvals formatting. Dissent is empty when review did not run."""

from __future__ import annotations

from typing import Any

from core.config import Settings
from core.gate.review import ReviewResult
from core.watch.alert import alert


def format_approval_message(
    intent_id: str,
    classification: str,
    intent: dict[str, Any],
    review: ReviewResult,
    *,
    hold_until: str | None = None,
) -> str:
    lines = [
        f"{intent_id} | {classification.upper()} | {intent.get('kind')}",
        f"venture={intent.get('venture') or intent.get('venture_id') or '-'}",
        f"rationale={(intent.get('rationale') or '')[:240]}",
    ]
    if not review.available:
        lines.append("REVIEW UNAVAILABLE")
    elif review.dissent:
        lines.append(f"dissent: {review.dissent[:500]}")
    if hold_until and classification == "amber":
        lines.append(f"auto-execute: {hold_until}")
    return "\n".join(lines)


def post_approval(
    settings: Settings,
    intent_id: str,
    intent: dict[str, Any],
    classification: str,
    review: ReviewResult,
    *,
    hold_until: str | None = None,
) -> None:
    msg = format_approval_message(intent_id, classification, intent, review, hold_until=hold_until)
    alert(settings.paths, msg, "approvals")
