"""Alerts go to Slack. A file on a laptop is not an alert."""

from __future__ import annotations

import json
from typing import Any

from core.db import utcnow
from core.paths import Paths

DEDUPE_SECONDS = 900


def alert(paths: Paths, message: str, channel: str = "status") -> bool:
    """Post to Slack. Returns True only if Slack accepted the message."""
    cid = _channel_id(paths, channel)
    if not cid:
        _undelivered(paths, message, channel, "no channel id")
        return False
    try:
        from core.drivers.messaging.slack import SlackDriver

        SlackDriver().post(
            cid,
            [{"type": "section", "text": {"type": "mrkdwn", "text": message[:2900]}}],
        )

        return True
    except Exception as exc:  # noqa: BLE001
        _undelivered(paths, message, channel, str(exc))
        return False


def alert_once(paths: Paths, key: str, message: str, channel: str = "status") -> bool:
    """Same key is not re-sent until DEDUPE_SECONDS elapse."""
    if _deduped(paths, key):
        return False
    ok = alert(paths, message, channel)
    if ok:
        _mark(paths, key)
    return ok


def _channel_id(paths: Paths, slug: str) -> str:
    try:
        import yaml

        if not paths.sabre_yaml.exists():
            return ""
        cfg = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
        ids = cfg.get("channel_ids") or {}
        return str(ids.get(slug) or "")
    except Exception:
        return ""


def _state_path(paths: Paths):
    paths.runtime.mkdir(parents=True, exist_ok=True)
    return paths.runtime / "alert-state.json"


def _load_state(paths: Paths) -> dict[str, Any]:
    path = _state_path(paths)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _deduped(paths: Paths, key: str) -> bool:
    from datetime import UTC, datetime

    raw = (_load_state(paths).get(key) or {}).get("at")
    if not raw:
        return False
    try:
        ts = datetime.fromisoformat(str(raw))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return (datetime.now(UTC) - ts).total_seconds() < DEDUPE_SECONDS
    except ValueError:
        return False


def _mark(paths: Paths, key: str) -> None:
    state = _load_state(paths)
    state[key] = {"at": utcnow()}
    path = _state_path(paths)
    path.write_text(json.dumps(state), encoding="utf-8")


def _undelivered(paths: Paths, message: str, channel: str, error: str) -> None:
    """Audit of a failed delivery. This is not the alert."""
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        with (paths.logs / "alert-undelivered.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({"at": utcnow(), "channel": channel, "message": message, "error": error}) + "\n"
            )
    except Exception:
        pass
