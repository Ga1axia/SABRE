from __future__ import annotations

import os
from typing import Any

from core.config import load_settings, write_yaml
from core.drivers.inference.openai_compat import OpenAICompatDriver
from core.envfile import set_env_values
from core.runtime.hermes import write_hermes_layout
from core.setup.prompt import ask, os_noninteractive

number = 5
name = "Inference"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {
            "provider": "openai_compat",
            "base_url": os.environ.get("SABRE_INFERENCE_BASE_URL") or "https://api.openai.com/v1",
            "key": os.environ.get("SABRE_INFERENCE_KEY") or os.environ.get("OPENAI_API_KEY") or "",
            "model": "gpt-4.1-mini",
        }
    provider = ask("Provider (openai_compat)", "openai_compat")
    base = ask("Base URL", os.environ.get("SABRE_INFERENCE_BASE_URL") or "https://api.openai.com/v1")
    existing = os.environ.get("SABRE_INFERENCE_KEY") or ""
    key = ask("API key (visible; rotate if this terminal is logged)", existing)
    model = ask("Core model id", "gpt-4.1-mini")
    print("       Set a hard spend cap at the provider. SABRE's daily cap is not the outermost brake.")
    return {"provider": provider, "base_url": base, "key": key, "model": model}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    paths = ctx["paths"]
    updates = {}
    if answers.get("key"):
        updates["SABRE_INFERENCE_KEY"] = answers["key"]
    if answers.get("base_url"):
        updates["SABRE_INFERENCE_BASE_URL"] = answers["base_url"]
    if updates:
        set_env_values(paths, updates)
    import yaml

    cfg = {}
    if paths.sabre_yaml.exists():
        cfg = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
    drivers = cfg.setdefault("drivers", {})
    drivers["inference"] = {
        "name": answers.get("provider") or "openai_compat",
        "model_core": answers.get("model") or "gpt-4.1-mini",
        "model_worker": "gpt-4.1-mini",
        "model_review": "gpt-4.1-mini",
    }
    write_yaml(paths.sabre_yaml, cfg)
    write_hermes_layout(paths, load_settings(paths))


def verify(ctx: dict[str, Any]) -> str | None:
    key = os.environ.get("SABRE_INFERENCE_KEY")
    if not key:
        return "SABRE_INFERENCE_KEY missing (set it or re-run this step)"
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return None
    try:
        driver = OpenAICompatDriver()
        result = driver.complete(
            [{"role": "user", "content": "Reply with the single word pong."}],
            model="gpt-4.1-mini",
        )
        if not result.text:
            return "live completion returned empty text"
        driver.usage("1970-01-01")
    except Exception as exc:  # noqa: BLE001
        return f"live completion failed: {exc} — check key/base URL"
    return None
