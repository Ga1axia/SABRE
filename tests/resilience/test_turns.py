from __future__ import annotations

from core.runtime.turns import claim, complete, enqueue, list_turns, recover


def test_crash_mid_turn_resumes_same_payload(sabre_home):
    first = enqueue(sabre_home, {"user_message": "keep this"}, session_id="sess-crash")
    leased = claim(sabre_home, actor="hermes", lease_seconds=-1)
    assert leased is not None
    assert leased["id"] == first["id"]
    assert leased["status"] == "leased"
    n = recover(sabre_home)
    assert n == 1
    again = claim(sabre_home, actor="hermes")
    assert again is not None
    assert again["id"] == first["id"]
    assert again["payload"]["user_message"] == "keep this"
    assert again["attempts"] == 2
    complete(sabre_home, again["id"])
    done = [t for t in list_turns(sabre_home) if t["id"] == first["id"]][0]
    assert done["status"] == "done"
