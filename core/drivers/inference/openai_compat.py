from __future__ import annotations

import os
from typing import Any

from core.drivers import Completion, Usage
from core.drivers.inference.pricing import estimate_cost_cents
from core.errors import SabreError


class OpenAICompatDriver:
    name = "openai_compat"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **_: Any,
    ):
        self.api_key = api_key or os.environ.get("SABRE_INFERENCE_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (
            base_url
            or os.environ.get("SABRE_INFERENCE_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")

    def complete(self, messages, model, tools=None) -> Completion:
        if not self.api_key:
            raise SabreError("inference key missing", remedy="sabre setup --step 5")
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}"}
        from core.net import request as net_request

        r = net_request(
            "POST",
            f"{self.base_url}/chat/completions",
            circuit="inference",
            json=payload,
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = data.get("usage") or {}
        tin = int(usage.get("prompt_tokens") or 0)
        tout = int(usage.get("completion_tokens") or 0)
        provider = data.get("cost") or usage.get("cost")
        provider_cents = int(round(float(provider) * 100)) if provider else None
        cost = estimate_cost_cents(model, tin, tout, provider_cost_cents=provider_cents)
        return Completion(text=text, tokens_in=tin, tokens_out=tout, cost_cents=cost, model=model)

    def usage(self, since: str) -> Usage:
        from core.net import request as net_request

        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            r = net_request(
                "GET",
                f"{self.base_url}/usage?since={since}",
                circuit="inference",
                profile="probe",
                headers=headers,
                timeout=20,
            )
            if r.status_code >= 400:
                return Usage(cost_cents=None)
            data = r.json()
            tin = int(data.get("prompt_tokens") or 0)
            tout = int(data.get("completion_tokens") or 0)
            provider = data.get("cost")
            provider_cents = int(round(float(provider) * 100)) if provider else None
            cost = estimate_cost_cents(None, tin, tout, provider_cost_cents=provider_cents)
            return Usage(cost_cents=cost, tokens_in=tin, tokens_out=tout)
        except Exception:
            return Usage(cost_cents=None)
