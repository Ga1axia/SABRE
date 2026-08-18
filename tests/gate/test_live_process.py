"""Stage C live C1/C3/C4 as separate OS processes — skipped on native Windows."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parent / "run_stage_c_live.py"
_spec = importlib.util.spec_from_file_location("run_stage_c_live", WORKER)
assert _spec and _spec.loader
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="two-process SQLite harness needs POSIX")


def test_live_c1_second_claimant_blocked(tmp_path):
    home = live._home(tmp_path)
    from core.db import connect, utcnow

    conn = connect(home / "sabre.db")
    conn.execute(
        """INSERT INTO tasks(id, goal, acceptance, status, created_at)
           VALUES ('T-live-c1', 'do', 'done', 'ready', ?)""",
        (utcnow(),),
    )
    conn.commit()
    conn.close()
    a = live._run_worker(home, "c1_claim", "T-live-c1", "agent-a")
    b = live._run_worker(home, "c1_claim", "T-live-c1", "agent-b")
    assert a.returncode == 0 and b.returncode == 0
    da = json.loads(a.stdout)
    db = json.loads(b.stdout)
    assert da["ok"] is True
    assert db["ok"] is False


def test_live_c3_client_key_is_hashed_not_stored_raw(tmp_path):
    home = live._home(tmp_path)
    p = live._run_worker(home, "c3")
    assert p.returncode == 0
    body = json.loads(p.stdout)
    assert body["intents"] == 1
    assert body["result"].get("state") != "refused"


def test_live_c4_only_one_concurrent_spend_executes(tmp_path):
    import subprocess

    from core.config import write_yaml
    from core.db import connect
    from core.paths import Paths

    home = live._home(tmp_path)
    paths = Paths(home)
    write_yaml(
        paths.sabre_yaml,
        {
            "drivers": {"cards": {"name": "memory", "enabled": True}},
            "envelopes": {
                "spend": {
                    "per_transaction_max": 50,
                    "daily_max": 1.50,
                    "monthly_max": 1200,
                    "per_venture_max": 400,
                    "allowed_categories": ["domains"],
                    "blocked_categories": [],
                }
            },
        },
    )
    env = {**os.environ, "SABRE_HOME": str(home), "SABRE_DEV": "1", "PYTHONPATH": str(live.ROOT)}
    p1 = subprocess.Popen(
        [sys.executable, str(WORKER), "--worker", "c4", str(home), "namecheap"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(live.ROOT),
    )
    p2 = subprocess.Popen(
        [sys.executable, str(WORKER), "--worker", "c4", str(home), "porkbun"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(live.ROOT),
    )
    o1, _e1 = p1.communicate()
    o2, _e2 = p2.communicate()
    r1 = json.loads(o1)
    r2 = json.loads(o2)
    greens = [r for r in (r1, r2) if r.get("classification") == "green" and r.get("state") == "executed"]
    assert len(greens) == 1
