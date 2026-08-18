"""Launch Hermes. Slack, sessions, memory, and tools belong to Hermes — not this process."""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from core.config import load_settings
from core.envfile import load_env
from core.gate.client import gate_get, gate_post
from core.paths import Paths, default_home
from core.runtime.hermes import hermes_process_env, resolve_hermes_bin, write_hermes_layout
from core.runtime.slash import handle_slash
from core.runtime.turns import recover
from core.watch.killswitch import is_killed

__all__ = ["handle_slash", "preflight", "run"]


def preflight(paths: Paths) -> str | None:
    if is_killed(paths):
        return "Kill switch engaged. I will not act until sabre unkill."
    if not resolve_hermes_bin():
        return "hermes binary not found. Run install.sh or set SABRE_HERMES_BIN."
    health = gate_get(paths, "/v1/health")
    if health.get("error") or not health.get("ok"):
        return "Gate unreachable. I refuse to run ungated."
    return None


def _beat_loop(paths: Paths) -> None:
    interval = 300
    try:
        interval = int(load_settings(paths).raw.get("heartbeat_seconds") or 300)
    except Exception:
        pass
    while True:
        try:
            gate_post(paths, "/v1/heartbeat", {"service": "agent"})
        except Exception:
            pass
        time.sleep(interval)


def run() -> None:
    paths = Paths(default_home())
    load_env(paths)
    settings = load_settings(paths)
    write_hermes_layout(paths, settings)
    recover(paths)
    reason = preflight(paths)
    if reason:
        print(f"sabre-agent: {reason}", file=sys.stderr)
        raise SystemExit(1)
    bin_path = resolve_hermes_bin()
    assert bin_path is not None
    env = hermes_process_env(paths)
    threading.Thread(target=_beat_loop, args=(paths,), daemon=True).start()
    raise SystemExit(subprocess.call([bin_path, "gateway", "run"], env=env, cwd=str(paths.work)))


if __name__ == "__main__":
    run()
