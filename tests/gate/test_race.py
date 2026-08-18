from __future__ import annotations

from threading import Thread

from core.config import load_settings, write_yaml
from core.db import connect
from core.gate.submit import submit_intent


def test_concurrent_spends_cannot_both_pass_daily_ceiling(sabre_home):
    write_yaml(
        sabre_home.sabre_yaml,
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
    settings = load_settings(sabre_home)
    results: list[dict] = []

    def worker(vendor: str) -> None:
        conn = connect(sabre_home.db)
        try:
            body = {
                "kind": "spend",
                "venture": "geo-audit",
                "payload": {
                    "category": "domains",
                    "amount_cents": 100,
                    "vendor": vendor,
                    "description": vendor,
                },
                "rationale": "domain",
            }
            results.append(submit_intent(settings, conn, body))
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            results.append({"error": str(exc), "state": "failed"})
            conn.rollback()
        finally:
            conn.close()

    t1 = Thread(target=worker, args=("namecheap",))
    t2 = Thread(target=worker, args=("porkbun",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    greens = [r for r in results if r.get("classification") == "green" and r.get("state") == "executed"]
    reds = [r for r in results if r.get("classification") == "red"]
    assert len(results) == 2
    assert len(greens) == 1
    assert len(reds) == 1
    conn = connect(sabre_home.db)
    debit = conn.execute(
        "SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE direction='debit'"
    ).fetchone()[0]
    conn.close()
    assert debit == 100
