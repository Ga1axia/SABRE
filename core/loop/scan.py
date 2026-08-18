"""Daily opportunity scan. Scores candidates; does not open SQLite."""

from __future__ import annotations

import json
from typing import Any

from core.paths import Paths

SCAN_DIR = "opportunities"


def score_candidate(candidate: dict[str, Any], promoted_skills: set[str]) -> float:
    """Higher is better. Skill reuse is weighted so the engine compounds."""
    ttfd = float(candidate.get("ttfd_days") or 30)
    spend = float(candidate.get("spend_to_first_dollar_cents") or 50_000)
    evidence = min(max(float(candidate.get("evidence") or 0), 0.0), 1.0)
    names = {str(s) for s in (candidate.get("skills") or [])}
    reuse = len(names & promoted_skills)
    return evidence * 40.0 + reuse * 30.0 + max(0.0, 21.0 - ttfd) + max(0.0, 10.0 - spend / 10_000.0)


def _provenance_ok(data: dict[str, Any]) -> bool:
    prov = data.get("provenance")
    if not isinstance(prov, list) or not prov:
        return False
    for item in prov:
        if isinstance(item, dict) and item.get("source") and item.get("at"):
            return True
    return False


def scan(paths: Paths, promoted_skills: set[str] | None = None) -> dict[str, Any]:
    dest = paths.work / SCAN_DIR
    dest.mkdir(parents=True, exist_ok=True)
    promoted = promoted_skills if promoted_skills is not None else _promoted_from_disk(dest)
    ranked: list[dict[str, Any]] = []
    for path in sorted(dest.glob("*.json")):
        if path.name == "ranked.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if not _provenance_ok(data):
            continue
        data["score"] = round(score_candidate(data, promoted), 2)
        ranked.append(data)
    ranked.sort(key=lambda c: float(c.get("score") or 0), reverse=True)
    (dest / "ranked.json").write_text(json.dumps({"candidates": ranked}, indent=2) + "\n", encoding="utf-8")
    return {"candidates": ranked}


def _promoted_from_disk(dest) -> set[str]:
    path = dest / "promoted-skills.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        return {str(x) for x in (data.get("skills") or [])}
    return set()
