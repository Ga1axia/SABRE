"""Phase 2: backoff, circuit, Slack alert, resume. Fake clock compresses a 10-minute outage."""

from __future__ import annotations

from core import net as netmod
from core.config import write_yaml
from core.errors import CircuitOpen, RetryableError
from core.net import THRESHOLD, call, reset_for_tests, set_hooks


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += float(seconds)


def test_inference_black_hole_backoff_alert_resume(sabre_home, monkeypatch):
    write_yaml(sabre_home.sabre_yaml, {"channel_ids": {"status": "CSTAT"}})
    clock = FakeClock()
    monkeypatch.setattr(netmod, "TIME", clock.time)
    monkeypatch.setattr(netmod, "SLEEP", clock.sleep)
    monkeypatch.setattr(netmod, "RANDOM", lambda: 0.5)
    reset_for_tests()

    timeline: list[tuple[float, str]] = []
    posted: list[str] = []
    monkeypatch.setattr(
        "core.drivers.messaging.slack.SlackDriver.post",
        lambda self, channel, blocks: posted.append(str(blocks[0]["text"]["text"])) or "ts",
    )

    def on_open(name: str) -> None:
        timeline.append((clock.t, f"circuit_open:{name}"))
        from core.watch.alert import alert_once

        alert_once(sabre_home, f"circuit:{name}:open", f"{name} circuit open", "status")

    def on_close(name: str) -> None:
        timeline.append((clock.t, f"circuit_close:{name}"))
        from core.watch.alert import alert_once

        alert_once(sabre_home, f"circuit:{name}:close", f"{name} resumed", "status")

    set_hooks(on_open=on_open, on_close=on_close)

    def black_hole() -> str:
        timeline.append((clock.t, "retry"))
        raise RetryableError("inference black hole")

    try:
        call(black_hole, circuit="inference", profile="rpc")
        raise AssertionError("black hole should not succeed")
    except RetryableError:
        timeline.append((clock.t, "call_exhausted"))

    assert any(e.startswith("circuit_open:") for _, e in timeline)
    assert clock.sleeps, "expected backoff sleeps"
    assert all(s >= 0 for s in clock.sleeps)
    assert posted and "circuit open" in posted[0]
    assert not (sabre_home.logs / "alerts.jsonl").exists()

    try:
        call(black_hole, circuit="inference", profile="rpc")
        raise AssertionError("open circuit must fail fast")
    except CircuitOpen:
        timeline.append((clock.t, "fail_fast"))

    clock.t += 600
    timeline.append((clock.t, "t_plus_10min"))

    def restored() -> str:
        timeline.append((clock.t, "success"))
        return "pong"

    assert call(restored, circuit="inference", profile="rpc") == "pong"
    assert any(e.startswith("circuit_close:") for _, e in timeline)
    assert any("resumed" in p for p in posted)
    assert THRESHOLD >= 3
    print("PHASE2_TIMELINE", timeline)
    print("PHASE2_SLEEPS", clock.sleeps)
    print("PHASE2_ALERTS", posted)
