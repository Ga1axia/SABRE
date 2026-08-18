"""Adversarial review on a different model/provider than core. Advisory dissent only."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.config import Settings
from core.paths import core_dir


def review_intent(settings: Settings, intent: dict[str, Any], klass: str) -> str:
    inf = settings.drivers.get("inference") or {}
    review_model = str(inf.get("model_review") or "gpt-4.1-mini")
    core_model = str(inf.get("model_core") or "gpt-4.1")
    review_key = os.environ.get("SABRE_REVIEW_KEY") or ""
    review_base = os.environ.get("SABRE_REVIEW_BASE_URL") or ""
    core_base = os.environ.get("SABRE_INFERENCE_BASE_URL") or ""
    if not review_key:
        if os.environ.get("SABRE_SKIP_LIVE") == "1":
            return f"review skipped: configure SABRE_REVIEW_KEY for live adversarial review ({klass} {intent.get('kind')})"
        return "review unavailable: SABRE_REVIEW_KEY missing"
    if review_base and core_base and review_base.rstrip("/") == core_base.rstrip("/") and review_key == (
        os.environ.get("SABRE_INFERENCE_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    ):
        return (
            f"review misconfigured: review provider must differ from core "
            f"({review_model} vs {core_model})"
        )
    persona = _load_persona()
    prompt = (
        f"{persona}\n\n"
        "Find reasons this plan fails. Write a short dissent. Do not approve it.\n\n"
        f"{intent.get('kind')}: {intent.get('rationale')}\n{intent.get('payload')}"
    )
    try:
        from core.drivers.inference.openai_compat import OpenAICompatDriver

        driver = OpenAICompatDriver(api_key=review_key, base_url=review_base or None)
        completion = driver.complete([{"role": "user", "content": prompt}], review_model)
        text = (completion.text or "").strip()
        return text or f"empty dissent from {review_model}"
    except Exception as exc:  # noqa: BLE001
        return f"review unavailable ({review_model}): {exc}"


def _load_persona() -> str:
    path = core_dir() / "runtime" / "personas" / "reality-checker.md"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return "You are a reality-check reviewer."
