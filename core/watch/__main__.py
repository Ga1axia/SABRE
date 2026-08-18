"""Heartbeat monitor, kill switch, remote-kill poll. Sole writer of the kill file."""

from __future__ import annotations

import os
import threading
import time

from core.config import load_settings
from core.db import connect
from core.envfile import load_env
from core.errors import RetryableError
from core.gate.ledger import expire_held_red
from core.gate.reconcile import reconcile
from core.gate.submit import effect_drivers
from core.net import request as net_request
from core.net import set_hooks
from core.paths import Paths, default_home
from core.watch.alert import alert, alert_once
from core.watch.control import bind
from core.watch.heartbeat import beat, missed_heartbeats
from core.watch.killswitch import engage, is_killed


def _wire_circuit_alerts(paths: Paths) -> None:
    def on_open(name: str) -> None:
        if name == "slack":
            return
        alert_once(paths, f"circuit:{name}:open", f"{name} circuit open", "status")

    def on_close(name: str) -> None:
        if name == "slack":
            return
        alert_once(paths, f"circuit:{name}:close", f"{name} resumed", "status")

    set_hooks(on_open=on_open, on_close=on_close)


def _probe_inference(paths: Paths) -> None:
    key = os.environ.get("SABRE_INFERENCE_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return
    base = (os.environ.get("SABRE_INFERENCE_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    try:
        net_request(
            "GET",
            f"{base}/models",
            circuit="inference",
            profile="probe",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
    except RetryableError:
        pass


def run() -> None:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    _wire_circuit_alerts(paths)
    httpd = bind(settings)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    interval = int(settings.raw.get("watch_poll_seconds") or 30)
    while True:
        beat(paths, "watch")
        if is_killed(paths):
            alert_once(paths, "kill", "kill switch engaged", "status")
        for svc, age in missed_heartbeats(paths):
            alert_once(
                paths,
                f"heartbeat:{svc}",
                f"missed heartbeat: {svc} silent {int(age)}s",
                "status",
            )
        _probe_inference(paths)
        if paths.db.exists():
            conn = connect(paths.db)
            try:
                n = expire_held_red(conn, settings.red_expire_days)
                if n:
                    alert(paths, f"expired {n} held red intents", "status")
                report = reconcile(effect_drivers(settings), conn, paths=paths)
                conn.commit()
                if report.get("divergences"):
                    alert(paths, f"reconcile diverged: {len(report['divergences'])}", "status")
            finally:
                conn.close()
        mirror = os.environ.get("SABRE_MIRROR_URL")
        token = os.environ.get("SABRE_MIRROR_TOKEN")
        if mirror and token:
            try:
                r = net_request(
                    "GET",
                    f"{mirror.rstrip('/')}/kill",
                    circuit="mirror",
                    profile="probe",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if r.status_code == 200 and r.json().get("kill"):
                    engage(paths)
                    alert(paths, "remote kill flag set", "status")
            except RetryableError:
                pass
        time.sleep(interval)


if __name__ == "__main__":
    run()
