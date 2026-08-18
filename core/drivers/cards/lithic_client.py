"""Lithic sandbox/production HTTP client. Charges fail at Lithic, not in SABRE."""

from __future__ import annotations

import os
from typing import Any

import httpx

from core.errors import SabreError


class LithicDeclined(SabreError):
    """Issuer declined the authorization (HTTP 422 from Lithic simulate/authorize)."""


class LithicClient:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("SABRE_LITHIC_API_KEY") or ""
        self.base_url = (base_url or os.environ.get("SABRE_LITHIC_BASE_URL") or "https://sandbox.lithic.com").rstrip("/")
        if not self.api_key:
            raise SabreError("Lithic API key missing", remedy="set SABRE_LITHIC_API_KEY")

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": self.api_key, "Accept": "application/json"}
        if kwargs.get("json") is not None:
            headers["Content-Type"] = "application/json"
        with httpx.Client(base_url=self.base_url, timeout=30.0) as client:
            return client.request(method, path, headers=headers, **kwargs)

    def create_card(self, *, spend_limit_cents: int) -> dict[str, Any]:
        r = self._request(
            "POST",
            "/v1/cards",
            json={
                "type": "VIRTUAL",
                "spend_limit": int(spend_limit_cents),
                "spend_limit_duration": "FOREVER",
            },
        )
        if r.status_code >= 400:
            raise SabreError(f"Lithic card create failed: {r.status_code} {r.text[:500]}")
        data = r.json()
        if not isinstance(data, dict):
            raise SabreError("Lithic card create returned non-object")
        return data

    def simulate_authorize(self, *, pan: str, amount_cents: int, descriptor: str = "SABRE") -> dict[str, Any]:
        r = self._request(
            "POST",
            "/v1/simulate/authorize",
            json={"pan": pan, "amount": int(amount_cents), "descriptor": descriptor[:25]},
        )
        if r.status_code == 422:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            message = ""
            if isinstance(body, dict):
                message = str(body.get("message") or body.get("error") or r.text)
            else:
                message = r.text
            raise LithicDeclined(message or "Lithic declined authorization", remedy="reduce amount or raise card limit")
        if r.status_code >= 400:
            raise SabreError(f"Lithic authorize failed: {r.status_code} {r.text[:500]}")
        data = r.json()
        return data if isinstance(data, dict) else {"raw": data}

    def list_transactions(self, *, card_token: str, since: str) -> list[dict[str, Any]]:
        r = self._request("GET", "/v1/transactions", params={"card_token": card_token, "begin": since})
        if r.status_code >= 400:
            raise SabreError(f"Lithic list transactions failed: {r.status_code} {r.text[:500]}")
        data = r.json()
        if isinstance(data, dict):
            rows = data.get("data") or data.get("transactions") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        return [row for row in rows if isinstance(row, dict)]

    def close_card(self, token: str) -> None:
        r = self._request("PATCH", f"/v1/cards/{token}", json={"state": "CLOSED"})
        if r.status_code >= 400:
            raise SabreError(f"Lithic close card failed: {r.status_code} {r.text[:300]}")

    def freeze_card(self, token: str) -> None:
        r = self._request("PATCH", f"/v1/cards/{token}", json={"state": "PAUSED"})
        if r.status_code >= 400:
            raise SabreError(f"Lithic freeze card failed: {r.status_code} {r.text[:300]}")
