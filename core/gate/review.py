"""Adversarial review on a different model/provider than core. Advisory dissent only."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import Settings
from core.paths import core_dir


@dataclass(frozen=True)
class ReviewResult:
    dissent: str
    available: bool


def review_intent(settings: Settings, intent: dict[str, Any], klass: str) -> ReviewResult:
    inf = settings.drivers.get("inference") or {}
    review_model = str(inf.get("model_review") or "gpt-4.1-mini")
    core_model = str(inf.get("model_core") or "gpt-4.1")
    review_key = os.environ.get("SABRE_REVIEW_KEY") or ""
    review_base = os.environ.get("SABRE_REVIEW_BASE_URL") or ""
    core_base = os.environ.get("SABRE_INFERENCE_BASE_URL") or ""
    if not review_key:
        return ReviewResult(dissent="", available=False)
    if review_base and core_base and review_base.rstrip("/") == core_base.rstrip("/") and review_key == (
        os.environ.get("SABRE_INFERENCE_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    ):
        return ReviewResult(dissent="", available=False)
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
        return ReviewResult(dissent=text or f"empty dissent from {review_model}", available=True)
    except Exception:  # noqa: BLE001
        return ReviewResult(dissent="", available=False)


def _load_persona() -> str:
    path = core_dir() / "runtime" / "personas" / "reality-checker.md"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return "You are a reality-check reviewer."
