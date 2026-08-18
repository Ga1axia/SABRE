from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.loop.discover import discover
from core.loop.scan import scan


def test_discover_writes_candidates_with_provenance(sabre_home):
    sample = [
        {
            "slug": "ai-widget",
            "title": "AI widget",
            "ttfd_days": 14,
            "spend_to_first_dollar_cents": 8000,
            "evidence": 0.5,
            "skills": [],
            "provenance": [{"source": "hn_algolia", "url": "https://example.com", "at": "t"}],
        }
    ]
    with patch("core.loop.discover._mine_hn", return_value=sample):
        out = discover(sabre_home)
    assert "ai-widget" in out["written"]
    path = sabre_home.work / "opportunities" / "ai-widget.json"
    assert path.exists()
    data = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert data["provenance"][0]["source"] == "hn_algolia"
    ranked = scan(sabre_home, set())
    assert any(c.get("slug") == "ai-widget" for c in ranked["candidates"])
