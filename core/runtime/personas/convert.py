"""Convert bundled persona markdown into runtime skills under $SABRE_HOME/personas."""

from __future__ import annotations

from pathlib import Path

from core.paths import Paths, core_dir


def bundled_personas() -> list[dict[str, str]]:
    d = core_dir() / "runtime" / "personas"
    out = []
    for p in sorted(d.glob("*.md")):
        title = p.stem.replace("_", "-")
        first = p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        out.append({"id": title, "name": first or title, "path": str(p)})
    return out


def convert_all(paths: Paths, enabled: list[str]) -> int:
    dest = paths.home / "personas"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in bundled_personas():
        if enabled and p["id"] not in enabled:
            continue
        src = Path(p["path"])
        (dest / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        n += 1
    return n
