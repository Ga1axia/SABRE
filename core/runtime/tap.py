"""Tool-call event hook. Non-blocking; logger failure never blocks work."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from core.gate.client import gate_post
from core.paths import Paths, default_home
from core.runtime.channels import inject_text, resolve_slug
from core.runtime.provenance import wrap_inbound
from core.runtime.redact import redact
from core.runtime.turns import attach_provenance

ARGS_CAP = 500


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def emit(paths, event: dict[str, Any]) -> None:
    try:
        if event.get("args"):
            event = {**event, "args": redact(str(event["args"]), paths)}
        gate_post(paths, "/v1/events", event)
    except Exception:
        _tap_failure(paths)


def handle_hook(payload: dict[str, Any], paths: Paths | None = None) -> dict[str, Any]:
    """Hermes hook: persist turns; tool calls also go to the gate and #logs."""
    paths = paths or Paths(default_home())
    event = str(payload.get("hook_event_name") or "post_tool_call")
    session_id = str(payload.get("session_id") or "")
    try:
        from core.runtime.submit_context import touch
        from core.runtime.turns import record_hook

        if session_id:
            touch(paths, session_id)
        record_hook(paths, payload)
    except Exception:
        _tap_failure(paths)
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    if event in {"pre_llm_call", "on_session_start"}:
        return _turn_context(paths, payload, extra)
    if event != "post_tool_call":
        return {}
    tool = str(payload.get("tool_name") or extra.get("tool_name") or "unknown")
    args = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    duration = extra.get("duration_ms") if extra.get("duration_ms") is not None else payload.get("duration_ms")
    err = extra.get("error") or payload.get("error")
    status = "error" if err else "ok"
    _maybe_alert_terminal_denial(paths, tool, args, err, extra, status)
    args_text = redact(_truncate(json.dumps(args, default=str)), paths)
    emit(
        paths,
        {
            "actor": "core",
            "tool": tool,
            "args": args_text,
            "status": status,
            "duration_ms": duration,
            "session_id": payload.get("session_id"),
            "trace_id": extra.get("task_id") or extra.get("tool_call_id") or payload.get("session_id"),
        },
    )
    line = {
        "tool": tool,
        "target": _target(args),
        "duration_ms": duration,
        "outcome": status,
        "args": args_text,
    }
    _mirror_logs(paths, line)
    return {}


def _maybe_alert_terminal_denial(
    paths: Paths,
    tool: str,
    args: dict[str, Any],
    err: Any,
    extra: dict[str, Any],
    status: str,
) -> None:
    if tool not in {"terminal", "shell", "run_terminal_cmd", "execute"}:
        return
    command = str(args.get("command") or args.get("cmd") or "")
    blob = " ".join(
        str(x)
        for x in (
            command,
            err,
            extra.get("error"),
            extra.get("result"),
            extra.get("output"),
            status,
        )
        if x
    ).lower()
    markers = ("blocked", "denied", "approval", "not approved", "consent", "timeout")
    if not any(m in blob for m in markers):
        return
    try:
        from core.watch.alert import alert_once

        key = f"terminal:denied:{hash(command) & 0xFFFF_FFFF}"
        alert_once(
            paths,
            key,
            f"terminal command denied (not on allowlist): `{command[:240]}`",
            "status",
        )
    except Exception:
        pass


def _turn_context(paths: Paths, payload: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    parts: list[str] = []
    slug = resolve_slug(paths, payload, extra)
    contract = inject_text(slug) if slug else ""
    if contract:
        parts.append(contract)
        try:
            from core.runtime.turns import set_channel

            set_channel(paths, str(payload.get("session_id") or ""), slug)
        except Exception:
            pass
    inbound = _inbound_context(paths, payload, extra)
    if inbound.get("context"):
        parts.append(str(inbound["context"]))
    if not parts:
        return {}
    return {"context": "\n\n".join(parts)}


def _inbound_context(paths: Paths, payload: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    sender = _sender(payload, extra)
    if not sender:
        return {}
    operator = os.environ.get("SABRE_OPERATOR_ID") or ""
    if operator and sender == operator:
        return {}
    message = str(extra.get("user_message") or payload.get("user_message") or extra.get("text") or "")
    wrapped = wrap_inbound(message, source="slack", sender=sender)
    attach_provenance(paths, str(payload.get("session_id") or ""), wrapped["provenance"])
    return {"context": wrapped["text"]}


def _sender(payload: dict[str, Any], extra: dict[str, Any]) -> str:
    for src in (extra, payload):
        for key in ("user", "user_id", "sender"):
            val = src.get(key)
            if val:
                return str(val)
    return ""


def _truncate(text: str, n: int = ARGS_CAP) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _target(args: dict[str, Any]) -> str:
    for key in ("command", "url", "path", "kind", "target"):
        if args.get(key):
            return _truncate(str(args[key]), 200)
    return ""


def _mirror_logs(paths: Paths, line: dict[str, Any]) -> None:
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        with (paths.logs / "logs-channel.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        _tap_failure(paths)
    cid = _logs_channel_id(paths)
    token = os.environ.get("SABRE_SLACK_BOT_TOKEN") or ""
    if not cid or not token:
        return
    try:
        from core.drivers.messaging.slack import SlackDriver

        text = (
            f"`{line.get('tool')}` {line.get('target') or ''} "
            f"{line.get('duration_ms')}ms {line.get('outcome')} {line.get('args')}"
        )
        SlackDriver().post(cid, [{"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}])
    except Exception:
        pass


def _logs_channel_id(paths: Paths) -> str:
    try:
        import yaml

        if not paths.sabre_yaml.exists():
            return ""
        cfg = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
        ids = cfg.get("channel_ids") or {}
        return str(ids.get("logs") or "")
    except Exception:
        return ""


def _tap_failure(paths) -> None:
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        with (paths.logs / "tap-failures.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _utcnow(), "error": "tap failed"}) + "\n")
    except Exception:
        pass
