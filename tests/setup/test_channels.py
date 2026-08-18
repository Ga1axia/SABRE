from __future__ import annotations

from core.setup.steps.channels import publish_and_pin


class _FakeSlack:
    def __init__(self) -> None:
        self.posts: list[tuple[str, list]] = []
        self.pins: list[tuple[str, str]] = []

    def post(self, channel: str, blocks: list) -> str:
        self.posts.append((channel, blocks))
        return f"ts-{channel}"

    def pin(self, channel_id: str, ts: str) -> None:
        self.pins.append((channel_id, ts))


def test_publish_and_pin_posts_verbatim_contract():
    fake = _FakeSlack()
    ids = {"directives": "CDIR", "requests": "CREQ"}
    errors = publish_and_pin(fake, ids)
    assert errors == []
    assert {c for c, _ in fake.posts} == {"CDIR", "CREQ"}
    assert fake.pins == [("CDIR", "ts-CDIR"), ("CREQ", "ts-CREQ")]
    dir_text = str(fake.posts[0][1][0]["text"]["text"])
    req_text = str(fake.posts[1][1][0]["text"]["text"])
    assert "24 hours" in dir_text
    assert "structurally cannot" in req_text
    assert "24 hours" not in req_text
