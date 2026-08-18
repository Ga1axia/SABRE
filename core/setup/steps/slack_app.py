from __future__ import annotations

import os
import webbrowser
from typing import Any

from core.envfile import set_env_values
from core.paths import core_dir
from core.setup.prompt import ask, os_noninteractive

number = 6
name = "Slack app"
optional = False

SLACK_APP_URL = "https://api.slack.com/apps?new_app=1"


def prompt(ctx: dict[str, Any]) -> dict[str, Any]:
    if os_noninteractive() or not ctx.get("interactive", True):
        return {
            "bot_token": os.environ.get("SABRE_SLACK_BOT_TOKEN") or "",
            "app_token": os.environ.get("SABRE_SLACK_APP_TOKEN") or "",
        }
    manifest = core_dir() / "slack" / "manifest.yaml.tmpl"
    print(f"       Manifest: {manifest}")
    print("       Create an app from that manifest, enable Socket Mode, install to the workspace.")
    print("       Changing scopes later requires reinstalling the app.")
    if confirm_open():
        webbrowser.open(SLACK_APP_URL)
    bot = ask("Bot token (xoxb-)", os.environ.get("SABRE_SLACK_BOT_TOKEN") or "")
    app = ask("App token (xapp-)", os.environ.get("SABRE_SLACK_APP_TOKEN") or "")
    return {"bot_token": bot, "app_token": app}


def confirm_open() -> bool:
    from core.setup.prompt import confirm

    return confirm("Open Slack app creation in the browser?", True)


def apply(ctx: dict[str, Any], answers: dict[str, Any]) -> None:
    updates = {}
    if answers.get("bot_token"):
        updates["SABRE_SLACK_BOT_TOKEN"] = answers["bot_token"]
    if answers.get("app_token"):
        updates["SABRE_SLACK_APP_TOKEN"] = answers["app_token"]
    if updates:
        set_env_values(ctx["paths"], updates)


def verify(ctx: dict[str, Any]) -> str | None:
    bot = os.environ.get("SABRE_SLACK_BOT_TOKEN")
    if not bot:
        return "SABRE_SLACK_BOT_TOKEN missing"
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return None
    try:
        from core.drivers.messaging.slack import SlackDriver

        SlackDriver().auth_test()
    except Exception as exc:  # noqa: BLE001
        return f"auth.test failed: {exc}"
    return None
