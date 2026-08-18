from __future__ import annotations

from core.config import write_yaml
from core.watch.alert import alert, alert_once


def test_alert_posts_to_slack_not_jsonl(sabre_home, monkeypatch):
    write_yaml(sabre_home.sabre_yaml, {"channel_ids": {"status": "CSTAT"}})
    posted = []

    def fake_post(self, channel, blocks):
        posted.append((channel, blocks))
        return "ts"

    monkeypatch.setattr("core.drivers.messaging.slack.SlackDriver.post", fake_post)
    assert alert(sabre_home, "inference circuit open", "status") is True
    assert posted == [("CSTAT", [{"type": "section", "text": {"type": "mrkdwn", "text": "inference circuit open"}}])]
    assert not (sabre_home.logs / "alerts.jsonl").exists()


def test_alert_without_channel_id_is_not_success(sabre_home):
    assert alert(sabre_home, "hello", "status") is False
    assert (sabre_home.logs / "alert-undelivered.jsonl").exists()
    assert not (sabre_home.logs / "alerts.jsonl").exists()


def test_alert_once_dedupes(sabre_home, monkeypatch):
    write_yaml(sabre_home.sabre_yaml, {"channel_ids": {"status": "CSTAT"}})
    posted = []
    monkeypatch.setattr(
        "core.drivers.messaging.slack.SlackDriver.post",
        lambda self, channel, blocks: posted.append(channel) or "ts",
    )
    assert alert_once(sabre_home, "circuit:inference:open", "down", "status") is True
    assert alert_once(sabre_home, "circuit:inference:open", "down", "status") is False
    assert posted == ["CSTAT"]
