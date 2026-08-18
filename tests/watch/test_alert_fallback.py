from __future__ import annotations

import json

from core.config import write_yaml
from core.setup.checks import check_alert_fallback
from core.watch.alert import alert_once, flush_queue, is_critical
from core.watch import alert_queue


def test_is_critical_classifies_heartbeat_and_reconcile():
    assert is_critical("heartbeat:agent", "missed heartbeat: agent silent 400s")
    assert is_critical("", "reconcile diverged: 2")
    assert not is_critical("circuit:inference:open", "inference circuit open")


def test_critical_alert_uses_fallback_when_slack_down(sabre_home, monkeypatch):
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "channel_ids": {"status": "CSTAT"},
            "alerts": {"fallback": {"name": "memory", "to": "ops@example.com"}},
        },
    )

    def boom(self, channel, blocks):
        raise RuntimeError("slack down")

    monkeypatch.setattr("core.drivers.messaging.slack.SlackDriver.post", boom)
    ok = alert_once(sabre_home, "heartbeat:agent", "missed heartbeat: agent silent 400s", "status")
    assert ok is True
    rows = [
        json.loads(line)
        for line in (sabre_home.runtime / "alert-fallback.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert "missed heartbeat" in rows[-1]["body"]


def test_both_channels_fail_queues_for_retry(sabre_home, monkeypatch):
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "channel_ids": {"status": "CSTAT"},
            "alerts": {"fallback": {"name": "memory", "to": "ops@example.com"}},
        },
    )

    monkeypatch.setattr("core.drivers.messaging.slack.SlackDriver.post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("slack")))
    monkeypatch.setattr("core.watch.alert._send_fallback", lambda *a, **k: False)
    ok = alert_once(sabre_home, "heartbeat:watch", "missed heartbeat: watch silent 900s", "status")
    assert ok is False
    assert alert_queue.queue_path(sabre_home).exists()


def test_flush_queue_retries_after_slack_recovers(sabre_home, monkeypatch):
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "channel_ids": {"status": "CSTAT"},
            "alerts": {"fallback": {"name": "memory", "to": "ops@example.com"}},
        },
    )
    alert_queue.enqueue(
        sabre_home,
        {"key": "heartbeat:agent", "message": "missed heartbeat: agent silent 400s", "channel": "status"},
    )
    posted: list[str] = []

    def fake_post(self, channel, blocks):
        posted.append(blocks[0]["text"]["text"])
        return "ts"

    monkeypatch.setattr("core.drivers.messaging.slack.SlackDriver.post", fake_post)
    n = flush_queue(sabre_home)
    assert n == 1
    assert posted
    assert not alert_queue.queue_path(sabre_home).exists()


def test_doctor_requires_fallback_when_money_drivers_enabled(sabre_home):
    from core.config import load_settings

    write_yaml(
        sabre_home.sabre_yaml,
        {"drivers": {"cards": {"name": "memory", "enabled": True}}},
    )
    settings = load_settings(sabre_home)
    ok, msg = check_alert_fallback(sabre_home, settings)
    assert ok is False
    assert "fallback" in msg.lower()


def test_doctor_passes_fallback_when_configured(sabre_home, monkeypatch):
    from core.config import load_settings

    monkeypatch.setenv("SABRE_SKIP_LIVE", "1")
    write_yaml(
        sabre_home.sabre_yaml,
        {
            "drivers": {"cards": {"name": "memory", "enabled": True}},
            "alerts": {"fallback": {"name": "memory", "to": "ops@example.com"}},
        },
    )
    settings = load_settings(sabre_home)
    ok, msg = check_alert_fallback(sabre_home, settings)
    assert ok is True
    assert "memory" in msg
