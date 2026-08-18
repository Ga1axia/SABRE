"""Per-channel speech acts. Contracts from core/channels/*.md are injected each turn."""

from __future__ import annotations

import sqlite3
from typing import Any

from core.paths import Paths, core_dir

REQUIRED = (
    "directives",
    "requests",
    "approvals",
    "status",
    "logs",
    "ventures",
    "postmortems",
    "revenue",
)


def contract_path(slug: str):
    return core_dir() / "channels" / f"{slug.lstrip('#')}.md"


def contract_body(slug: str) -> str:
    path = contract_path(slug)
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def inject_text(slug: str) -> str:
    body = contract_body(slug)
    if not body:
        return ""
    name = slug.lstrip("#")
    return (
        f"CHANNEL CONTRACT (#{name})\n"
        f"You are in #{name}. This is a speech act, not a topic. Follow it for this turn.\n\n"
        f"{body}"
    )


def resolve_slug(paths: Paths | None, payload: dict[str, Any], extra: dict[str, Any]) -> str:
    """Map Hermes session_id → Slack channel via HERMES_HOME/state.db sessions.chat_id.

    Hook stdin has no channel field. extra.channel / channel_id / channel_name are
    ignored even if present. Source: hermes_state.SessionDB sessions.chat_id
    (written by record_gateway_session_peer).
    """
    del extra
    if paths is None:
        return ""
    session_id = str(payload.get("session_id") or "").strip()
    chat_id = session_chat_id(paths, session_id)
    if not chat_id:
        return ""
    token = chat_id.lstrip("#").strip()
    if token in REQUIRED:
        return token
    ids = _channel_ids(paths)
    inverted = {str(cid): slug for slug, cid in ids.items()}
    return inverted.get(token, inverted.get(chat_id, ""))


def session_chat_id(paths: Paths, session_id: str) -> str:
    """Read sessions.chat_id from Hermes state.db. Empty if missing or unreadable."""
    if not session_id:
        return ""
    from core.runtime.hermes import hermes_home

    db = hermes_home(paths) / "state.db"
    if not db.is_file():
        return ""
    try:
        conn = sqlite3.connect(str(db), timeout=1.0)
    except sqlite3.Error:
        return ""
    try:
        try:
            conn.execute("PRAGMA query_only=ON")
        except sqlite3.Error:
            pass
        row = conn.execute("SELECT chat_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    except sqlite3.Error:
        return ""
    finally:
        conn.close()
    if not row:
        return ""
    return str(row[0] or "").strip()


def render_speech_act(slug: str, question: str) -> str:
    """Deterministic speech-act shape from the contract. Not an LLM."""
    name = slug.lstrip("#")
    if name == "directives":
        return (
            "Recommendation: treat this as a direction choice, not a permission gate.\n"
            "Reasoning: #directives asks for the operator's preference when paths look comparable, "
            "or when a decision would change what we pursue for weeks.\n"
            f"Question: {question}\n"
            "If no answer arrives within 24 hours, I will act on this recommendation and note that I did."
        )
    if name == "requests":
        return (
            f"Need: {question}\n"
            "Why I cannot do it: #requests is only for things I structurally cannot do "
            "(a signature, a phone call, an identity verification, a payment method, "
            "an account only the operator can open).\n"
            "Blocked until: nothing — this is not a structural blocker, so I will not wait here.\n"
            "Meanwhile: I keep working. Never ask permission here — that is #approvals. "
            "Never use this for something I could do with more effort."
        )
    body = contract_body(name)
    return f"#{name}\n{body}\n\nInput: {question}"


def _channel_ids(paths: Paths | None) -> dict[str, str]:
    if paths is None or not paths.sabre_yaml.exists():
        return {}
    try:
        import yaml

        cfg = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    ids = cfg.get("channel_ids") or {}
    return {str(k): str(v) for k, v in ids.items()} if isinstance(ids, dict) else {}
