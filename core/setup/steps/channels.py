from __future__ import annotations

import os
from typing import Any

from core.config import load_defaults, write_yaml
from core.runtime.channels import contract_body
from core.setup.prompt import confirm, os_noninteractive

number = 8
name = "Channels"
optional = False


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    names = list(load_defaults().get("channels") or [])
    if os_noninteractive() or not ctx.get("interactive", True):
        return {"names": names, "skip_live": True}
    print(f"       Will ensure: {', '.join('#'+n for n in names)}")
    confirm("Create missing channels, invite the bot, pin contracts?", True)
    return {"names": names, "skip_live": False}


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    names = answers.get("names") or load_defaults().get("channels")
    import yaml

    cfg = {}
    if ctx["paths"].sabre_yaml.exists():
        cfg = yaml.safe_load(ctx["paths"].sabre_yaml.read_text(encoding="utf-8")) or {}
    cfg["channels"] = names
    write_yaml(ctx["paths"].sabre_yaml, cfg)
    if answers.get("skip_live") or os.environ.get("SABRE_SKIP_LIVE") == "1":
        return
    from core.drivers.messaging.slack import SlackDriver

    driver = SlackDriver()
    ids = driver.ensure_channels(list(names))
    cfg["channel_ids"] = ids
    write_yaml(ctx["paths"].sabre_yaml, cfg)
    operator = os.environ.get("SABRE_OPERATOR_ID") or ""
    if operator:
        for cid in ids.values():
            driver.invite_user(cid, operator)
    errors = publish_and_pin(driver, ids)
    if errors:
        raise RuntimeError("channel contract pin failed: " + "; ".join(errors))


def publish_and_pin(driver: Any, ids: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for slug, cid in ids.items():
        body = contract_body(slug)
        text = f"*#{slug}*\n{body}"[:3000]
        try:
            ts = driver.post(cid, [{"type": "section", "text": {"type": "mrkdwn", "text": text}}])
            if ts:
                driver.pin(cid, ts)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"#{slug}: {exc}")
    return errors


def verify(ctx: dict[str, Any]) -> str | None:
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return None
    import yaml

    if not ctx["paths"].sabre_yaml.exists():
        return "channels not recorded"
    cfg = yaml.safe_load(ctx["paths"].sabre_yaml.read_text(encoding="utf-8")) or {}
    names = list(cfg.get("channels") or load_defaults().get("channels") or [])
    ids = dict(cfg.get("channel_ids") or {})
    missing = [n for n in names if n not in ids]
    if missing:
        return f"missing channel ids: {', '.join(missing)}"
    from core.drivers.messaging.slack import SlackDriver

    driver = SlackDriver()
    for slug, cid in ids.items():
        try:
            if not driver.is_member(cid):
                return f"bot not a member of #{slug}"
            if not driver.round_trip(cid):
                return f"round trip failed on #{slug}"
        except Exception as exc:  # noqa: BLE001
            return f"#{slug} unverified: {exc}"
    return None
