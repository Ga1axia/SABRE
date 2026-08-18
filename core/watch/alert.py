"""Alerts: Slack primary, independent fallback for critical events."""

from __future__ import annotations

import json
import os
from typing import Any

from core.db import utcnow
from core.paths import Paths
from core.watch import alert_queue

DEDUPE_SECONDS = 900

CRITICAL_KEY_PREFIXES = (
    "heartbeat:",
    "kill",
    "circuit:gate",
    "gate:",
    "envelope:",
    "card:",
    "isolation.",
)

CRITICAL_MESSAGE_MARKERS = (
    "missed heartbeat",
    "reconcile diverged",
    "reconcile divergence",
    "gate failure",
    "card ",
    "envelope ",
    "isolation ",
    "remote kill",
)


def is_critical(key: str, message: str) -> bool:
    k = (key or "").lower()
    m = (message or "").lower()
    for prefix in CRITICAL_KEY_PREFIXES:
        if k.startswith(prefix):
            return True
    for marker in CRITICAL_MESSAGE_MARKERS:
        if marker in m:
            return True
    return False


def alert(paths: Paths, message: str, channel: str = "status", *, key: str = "") -> bool:
    """Deliver an alert. Critical events escalate to the fallback channel."""
    return _deliver(paths, key, message, channel)


def alert_once(paths: Paths, key: str, message: str, channel: str = "status") -> bool:
    """Same key is not re-sent until DEDUPE_SECONDS elapse."""
    if _deduped(paths, key):
        return False
    ok = _deliver(paths, key, message, channel)
    if ok:
        _mark(paths, key)
    return ok


def flush_queue(paths: Paths) -> int:
    """Retry queued critical alerts (watch startup)."""

    def deliver(row: dict[str, Any]) -> bool:
        return _deliver(
            paths,
            str(row.get("key") or ""),
            str(row.get("message") or ""),
            str(row.get("channel") or "status"),
            from_queue=True,
        )

    return alert_queue.drain(paths, deliver)


def _deliver(
    paths: Paths,
    key: str,
    message: str,
    channel: str,
    *,
    from_queue: bool = False,
) -> bool:
    critical = is_critical(key, message)
    slack_ok = _send_slack(paths, message, channel)
    if slack_ok:
        return True
    if not critical:
        _undelivered(paths, message, channel, "slack failed", key=key)
        return False
    fallback_ok = _send_fallback(paths, key, message)
    if fallback_ok:
        return True
    if not from_queue:
        alert_queue.enqueue(
            paths,
            {"key": key, "message": message, "channel": channel, "error": "slack and fallback failed"},
        )
    _undelivered(paths, message, channel, "slack and fallback failed", key=key)
    return False


def _send_slack(paths: Paths, message: str, channel: str) -> bool:
    cid = _channel_id(paths, channel)
    if not cid:
        return False
    try:
        from core.drivers.messaging.slack import SlackDriver

        SlackDriver().post(
            cid,
            [{"type": "section", "text": {"type": "mrkdwn", "text": message[:2900]}}],
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _fallback_config(paths: Paths) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = _load_cfg(paths)
    alerts = cfg.get("alerts") if isinstance(cfg.get("alerts"), dict) else {}
    fb = alerts.get("fallback") if isinstance(alerts.get("fallback"), dict) else {}
    return cfg, fb


def _send_fallback(paths: Paths, key: str, message: str) -> bool:
    _, fb = _fallback_config(paths)
    name = fb.get("name") or os.environ.get("SABRE_ALERT_FALLBACK_DRIVER") or ""
    if not name:
        return False
    to = str(fb.get("to") or os.environ.get("SABRE_ALERT_EMAIL_TO") or "")
    if not to:
        return False
    try:
        from core.drivers.loader import load_driver

        kwargs = {k: v for k, v in fb.items() if k not in {"name", "to", "enabled"}}
        if name == "memory" and "path" not in kwargs:
            kwargs["path"] = paths.runtime / "alert-fallback.jsonl"
        driver = load_driver("alerts", name, **kwargs)
        subject = f"SABRE critical: {key or 'alert'}"[:200]
        driver.send(to, subject, message[:8000])
        return True
    except Exception:  # noqa: BLE001
        return False


def _load_cfg(paths: Paths) -> dict[str, Any]:
    try:
        import yaml

        if not paths.sabre_yaml.exists():
            return {}
        cfg = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _channel_id(paths: Paths, slug: str) -> str:
    cfg = _load_cfg(paths)
    ids = cfg.get("channel_ids") or {}
    return str(ids.get(slug) or "")


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


def _undelivered(paths: Paths, message: str, channel: str, error: str, *, key: str = "") -> None:
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        with (paths.logs / "alert-undelivered.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"at": utcnow(), "key": key, "channel": channel, "message": message, "error": error}
                )
                + "\n"
            )
    except Exception:
        pass
