"""Provider driver protocols. Nothing in core names a vendor."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class Card:
    id: str
    provider_ref: str
    limit_cents: int


@dataclass
class Balance:
    spent_cents: int
    remaining_cents: int
    limit_cents: int


@dataclass
class Charge:
    id: str
    amount_cents: int
    occurred_at: str
    payer_ref: str = ""
    card_id: str = ""


@dataclass
class Refund:
    id: str
    charge_id: str
    amount_cents: int
    occurred_at: str


@dataclass
class Event:
    kind: str
    payload: dict[str, Any]


@dataclass
class Deployment:
    id: str
    url: str
    project: str


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_cents: int | None = None
    model: str = ""


@dataclass
class Usage:
    cost_cents: int | None
    tokens_in: int = 0
    tokens_out: int = 0


@runtime_checkable
class CardDriver(Protocol):
    name: str

    def issue(self, venture: str, limit_cents: int) -> Card: ...
    def freeze(self, card_id: str) -> None: ...
    def close(self, card_id: str) -> None: ...
    def balance(self, card_id: str) -> Balance: ...
    def list_transactions(self, card_id: str, since: str) -> list[Charge]: ...
    def authorize(
        self,
        card_id: str,
        amount_cents: int,
        *,
        provider_ref: str = "",
        merchant: str = "",
    ) -> Charge: ...


@runtime_checkable
class PaymentDriver(Protocol):
    name: str

    def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> Event | None: ...
    def list_charges(self, since: str) -> list[Charge]: ...
    def refunds(self, since: str) -> list[Refund]: ...
    def is_internal_payer(self, charge: Charge) -> bool: ...


@runtime_checkable
class HostingDriver(Protocol):
    name: str

    def deploy(self, path: str, project: str) -> Deployment: ...
    def domains(self, project: str) -> list[str]: ...
    def teardown(self, project: str) -> None: ...


@runtime_checkable
class MessagingDriver(Protocol):
    name: str

    def post(self, channel: str, blocks: list) -> str: ...
    def react_listener(self, cb: Callable) -> None: ...
    def ensure_channels(self, names: list[str]) -> dict[str, str]: ...
    def auth_test(self) -> dict[str, Any]: ...


@runtime_checkable
class InferenceDriver(Protocol):
    name: str

    def complete(self, messages, model, tools=None) -> Completion: ...
    def usage(self, since: str) -> Usage: ...
