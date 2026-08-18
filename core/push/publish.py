"""Outbound snapshot publisher. Failures never stall the company."""

from __future__ import annotations

import os
import time

from core.config import load_settings
from core.envfile import load_env
from core.errors import RetryableError
from core.net import request as net_request
from core.paths import Paths, default_home
from core.push.project import project
from core.push.sign import ensure_keys, sign_snapshot
from core.watch.alert import alert


def publish_once(settings) -> None:
    url = os.environ.get("SABRE_MIRROR_URL")
    token = os.environ.get("SABRE_MIRROR_TOKEN")
    if not url or not token:
        return
    ensure_keys(settings.paths)
    envelope = sign_snapshot(settings.paths, project(settings))
    try:
        net_request(
            "POST",
            f"{url.rstrip('/')}/snapshot",
            circuit="mirror",
            json=envelope,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except RetryableError:
        alert(settings.paths, "snapshot publish failed", "status")


def run() -> None:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    interval = int(settings.raw.get("snapshot_seconds") or 60)
    while True:
        publish_once(settings)
        time.sleep(interval)


if __name__ == "__main__":
    run()
