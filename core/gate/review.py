"""Adversarial review on a different model/provider than core. Advisory dissent only."""

from __future__ import annotations

import os
from typing import Any

from core.config import Settings


def review_intent(settings: Settings, intent: dict[str, Any], klass: str) -> str:
    inf = settings.drivers.get("inference") or {}
    review_model = str(inf.get("model_review") or "gpt-4.1-mini")
    core_model = str(inf.get("model_core") or "gpt-4.1")
    review_base = os.environ.get("SABRE_REVIEW_BASE_URL") or os.environ.get("SABRE_INFERENCE_BASE_URL") or ""
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return (
            f"SKIP_LIVE dissent on {klass} {intent.get('kind')}: "
            f"review model {review_model} (core {core_model})"
        )
    prompt = (
        "You are a reality-check reviewer. Find reasons this plan fails. "
        "Write a short dissent. Do not approve it.\n\n"
        f"{intent.get('kind')}: {intent.get('rationale')}\n{intent.get('payload')}"
    )
    try:
        from core.drivers.inference.openai_compat import OpenAICompatDriver

        driver = OpenAICompatDriver(base_url=review_base or None)
        completion = driver.complete(
            [{"role": "user", "content": prompt}],
            review_model,
        )
        text = (completion.text or "").strip()
        return text or f"empty dissent from {review_model}"
    except Exception as exc:  # noqa: BLE001
        return f"review unavailable ({review_model}): {exc}"
