from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from core.errors import SabreError
from core.net import call as net_call


class SlackDriver:
    name = "slack"

    def __init__(self, bot_token: str | None = None, app_token: str | None = None, **_: Any):
        self.bot_token = bot_token or os.environ.get("SABRE_SLACK_BOT_TOKEN") or ""
        self.app_token = app_token or os.environ.get("SABRE_SLACK_APP_TOKEN") or ""
        self._client = None

    def _sdk(self):
        if self._client is None:
            if not self.bot_token:
                raise SabreError("Slack bot token missing", remedy="sabre setup --step 6")
            from slack_sdk import WebClient

            self._client = WebClient(token=self.bot_token)
        return self._client

    def _rpc(self, fn, *, profile: str = "rpc"):
        return net_call(fn, circuit="slack", profile=profile)

    def auth_test(self) -> dict[str, Any]:
        return dict(self._rpc(lambda: self._sdk().auth_test(), profile="probe"))

    def is_member(self, channel_id: str) -> bool:
        info = self._rpc(lambda: self._sdk().conversations_info(channel=channel_id))
        return bool((info.get("channel") or {}).get("is_member"))

    def post(self, channel: str, blocks: list) -> str:
        text = ""
        if blocks and isinstance(blocks[0], dict):
            text = str(blocks[0].get("text") or blocks[0].get("title") or "")
            if isinstance(text, dict):
                text = str(text.get("text") or "")

        def send() -> str:
            resp = self._sdk().chat_postMessage(channel=channel, blocks=blocks, text=text or "SABRE")
            return str(resp.get("ts") or "")

        return str(self._rpc(send, profile="alert"))

    def pin(self, channel_id: str, ts: str) -> None:
        self._rpc(lambda: self._sdk().pins_add(channel=channel_id, timestamp=ts))

    def history(self, channel_id: str, limit: int = 10) -> list[dict[str, Any]]:
        resp = self._rpc(lambda: self._sdk().conversations_history(channel=channel_id, limit=limit))
        return list(resp.get("messages") or [])

    def round_trip(self, channel_id: str) -> bool:
        ts = self.post(
            channel_id,
            [{"type": "section", "text": {"type": "mrkdwn", "text": "SABRE round-trip probe"}}],
        )
        if not ts:
            return False
        return any(str(m.get("ts") or "") == str(ts) for m in self.history(channel_id, limit=10))

    def react_listener(self, cb: Callable) -> None:
        # The agent process owns the Socket Mode loop; this registers the callback contract.
        self._on_reaction = cb

    def ensure_channels(self, names: list[str]) -> dict[str, str]:
        client = self._sdk()
        existing = client.conversations_list(types="public_channel,private_channel", limit=1000)
        by_name = {c["name"]: c["id"] for c in existing.get("channels") or []}
        out: dict[str, str] = {}
        for name in names:
            slug = name.lstrip("#")
            if slug in by_name:
                cid = by_name[slug]
            else:
                created = client.conversations_create(name=slug)
                cid = created["channel"]["id"]
            try:
                client.conversations_join(channel=cid)
            except Exception:
                pass
            out[slug] = cid
        return out

    def invite_user(self, channel_id: str, user_id: str) -> None:
        try:
            self._sdk().conversations_invite(channel=channel_id, users=user_id)
        except Exception:
            pass

    def lookup_user(self, user_id: str) -> dict[str, Any]:
        return dict(self._sdk().users_info(user=user_id).get("user") or {})
