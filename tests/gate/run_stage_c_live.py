"""Stage C live C1/C3/C4 as separate OS processes against one SQLite file."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _home(tmp: Path) -> Path:
    home = tmp / "sabre"
    os.environ["SABRE_HOME"] = str(home)
    os.environ["SABRE_DEV"] = "1"
    os.environ["SABRE_SKIP_LIVE"] = "1"
    os.environ["SABRE_NONINTERACTIVE"] = "1"
    os.environ["SABRE_GATE_INSECURE"] = "1"
    os.environ["PYTHONPATH"] = str(ROOT)
    from core.db import init_schema
    from core.paths import Paths
    from core.watch.killswitch import install_readonly

    paths = Paths(home)
    paths.ensure()
    init_schema(paths.db)
    install_readonly(paths)
    return home


def _run_worker(home: Path, fn: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__)), "--worker", fn, str(home), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "SABRE_HOME": str(home), "SABRE_DEV": "1", "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
        check=False,
    )


def worker_c1_claim(home: Path, task_id: str, actor: str) -> dict:
    from core.db import connect
    from core.gate.ledger import claim_task

    conn = connect(Path(home) / "sabre.db")
    ok = claim_task(conn, task_id, actor, lease_seconds=900)
    row = conn.execute(
        "SELECT claimed_by, lease_until FROM tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.commit()
    conn.close()
    return {"ok": ok, "claimed_by": row["claimed_by"], "lease_until": row["lease_until"]}


def worker_c3(home: Path) -> dict:
    from core.config import load_settings
    from core.db import connect
    from core.gate.submit import submit_intent
    from core.paths import Paths

    paths = Paths(Path(home))
    settings = load_settings(paths)
    conn = connect(paths.db)
    result = submit_intent(
        settings,
        conn,
        {
            "kind": "research",
            "venture": "geo-audit",
            "payload": {"query": "live-c3"},
            "idempotency_key": "fresh-random-key",
            "rationale": "scan",
        },
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    conn.close()
    return {"result": result, "intents": n}


def worker_c4(home: Path, vendor: str) -> dict:
    from core.config import load_settings
    from core.db import connect
    from core.gate.submit import submit_intent
    from core.paths import Paths

    paths = Paths(Path(home))
    settings = load_settings(paths)
    conn = connect(paths.db)
    try:
        result = submit_intent(
            settings,
            conn,
            {
                "kind": "spend",
                "venture": "geo-audit",
                "payload": {
                    "category": "domains",
                    "amount_cents": 100,
                    "vendor": vendor,
                    "description": vendor,
                },
                "rationale": "domain",
            },
        )
        conn.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        return {"error": str(exc), "state": "failed"}
    finally:
        conn.close()


def live_c1() -> None:
    from core.db import connect, utcnow

    tmp = Path(tempfile.mkdtemp())
    home = _home(tmp)
    conn = connect(Path(home) / "sabre.db")
    conn.execute(
        """INSERT INTO tasks(id, goal, acceptance, status, created_at)
           VALUES ('T-live-c1', 'do', 'done', 'ready', ?)""",
        (utcnow(),),
    )
    conn.commit()
    conn.close()
    a = _run_worker(home, "c1_claim", "T-live-c1", "agent-a")
    b = _run_worker(home, "c1_claim", "T-live-c1", "agent-b")
    print("=== LIVE C1 process A ===", a.returncode, a.stdout.strip(), a.stderr.strip())
    print("=== LIVE C1 process B ===", b.returncode, b.stdout.strip(), b.stderr.strip())
    da = json.loads(a.stdout)
    db = json.loads(b.stdout)
    verdict_a = "A claimed" if da["ok"] else "A missed"
    verdict_b = "B stole" if db["ok"] else "B blocked"
    print("=== LIVE C1 verdict ===", verdict_a, "|", verdict_b)


def live_c3() -> None:
    tmp = Path(tempfile.mkdtemp())
    home = _home(tmp)
    p = _run_worker(home, "c3")
    print("=== LIVE C3 ===", p.returncode, p.stdout.strip(), p.stderr.strip())


def live_c4() -> None:
    from core.config import write_yaml
    from core.db import connect
    from core.paths import Paths

    tmp = Path(tempfile.mkdtemp())
    home = _home(tmp)
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
    p1 = subprocess.Popen(
        [sys.executable, str(Path(__file__)), "--worker", "c4", str(home), "namecheap"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SABRE_HOME": str(home), "SABRE_DEV": "1", "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )
    p2 = subprocess.Popen(
        [sys.executable, str(Path(__file__)), "--worker", "c4", str(home), "porkbun"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SABRE_HOME": str(home), "SABRE_DEV": "1", "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )
    o1, e1 = p1.communicate()
    o2, e2 = p2.communicate()
    print("=== LIVE C4 process 1 ===", p1.returncode, o1.strip(), e1.strip())
    print("=== LIVE C4 process 2 ===", p2.returncode, o2.strip(), e2.strip())
    r1 = json.loads(o1)
    r2 = json.loads(o2)
    greens = [r for r in (r1, r2) if r.get("classification") == "green" and r.get("state") == "executed"]
    reds = [r for r in (r1, r2) if r.get("classification") == "red"]
    conn = connect(paths.db)
    debit = conn.execute(
        "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit'"
    ).fetchone()[0]
    conn.close()
    print("=== LIVE C4 greens ===", len(greens), "reds", len(reds), "debit", debit)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--worker"]:
        fn, home, *rest = argv[1:]
        if fn == "c1_claim":
            print(json.dumps(worker_c1_claim(Path(home), rest[0], rest[1])))
        elif fn == "c3":
            print(json.dumps(worker_c3(Path(home))))
        elif fn == "c4":
            print(json.dumps(worker_c4(Path(home), rest[0])))
        else:
            raise SystemExit(f"unknown worker {fn}")
        return 0
    live_c1()
    live_c3()
    live_c4()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
