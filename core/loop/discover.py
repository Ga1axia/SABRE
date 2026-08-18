"""Live-source opportunity discovery. Writes work/opportunities/*.json before scoring."""

from __future__ import annotations

import json
import re
from typing import Any

from core.db import utcnow
from core.paths import Paths

SCAN_DIR = "opportunities"
HN_SEARCH = "https://hn.algolia.com/api/v1/search"


def discover(paths: Paths) -> dict[str, Any]:
    """Fetch public signals and write candidate JSON files with provenance."""
    dest = paths.work / SCAN_DIR
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    errors: list[str] = []
    for candidate in _mine_hn():
        slug = str(candidate.get("slug") or "")
        if not slug:
            continue
        path = dest / f"{slug}.json"
        path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        written.append(slug)
    return {"written": written, "errors": errors, "at": utcnow()}


def _mine_hn() -> list[dict[str, Any]]:
    import httpx

    params = {
        "query": "saas",
        "tags": "story",
        "numericFilters": "points>20",
        "hitsPerPage": 8,
    }
    try:
        r = httpx.get(HN_SEARCH, params=params, timeout=20.0)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "slug": "discover-offline",
                "ttfd_days": 30,
                "spend_to_first_dollar_cents": 50_000,
                "evidence": 0.1,
                "skills": [],
                "provenance": [{"source": "discover", "error": str(exc), "at": utcnow()}],
            }
        ]
    hits = data.get("hits") if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or hit.get("story_title") or "")
        url = str(hit.get("url") or hit.get("story_url") or "")
        points = int(hit.get("points") or hit.get("story_points") or 0)
        slug = _slugify(title) or _slugify(str(hit.get("objectID") or "hn"))
        evidence = min(max(points / 100.0, 0.1), 1.0)
        out.append(
            {
                "slug": slug,
                "title": title[:200],
                "ttfd_days": 14 if points >= 50 else 21,
                "spend_to_first_dollar_cents": 8000 if points >= 50 else 12_000,
                "evidence": round(evidence, 2),
                "skills": ["landing-page"] if "landing" in title.lower() else [],
                "provenance": [
                    {
                        "source": "hn_algolia",
                        "url": url or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                        "title": title[:200],
                        "points": points,
                        "at": utcnow(),
                    }
                ],
            }
        )
    return out


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48]
