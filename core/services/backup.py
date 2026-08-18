from __future__ import annotations

import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from core.paths import Paths
from core.proxy.store import list_secrets


def create_backup(paths: Paths) -> Path:
    paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = paths.backups / f"sabre-{stamp}.tar.gz"
    manifest = {
        "secret_names": [r["name"] for r in list_secrets(paths)],
        "created": stamp,
    }
    tmp_manifest = paths.backups / f".manifest-{stamp}.json"
    tmp_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    with tarfile.open(dest, "w:gz") as tar:
        if paths.db.exists():
            tar.add(paths.db, arcname="sabre.db")
        if paths.config_dir.exists():
            tar.add(paths.config_dir, arcname="config")
        if paths.work.exists():
            tar.add(paths.work, arcname="work")
        tar.add(tmp_manifest, arcname="secret-names.json")
    tmp_manifest.unlink(missing_ok=True)
    return dest


def restore_backup(paths: Paths, snapshot: str, dry_run: bool = False) -> None:
    src = Path(snapshot)
    if not src.exists():
        src = paths.backups / snapshot
    if not src.exists():
        raise FileNotFoundError(snapshot)
    with tarfile.open(src, "r:gz") as tar:
        tar.getmembers()  # validates archive
        if dry_run:
            return
        try:
            tar.extractall(paths.home, filter="data")
        except TypeError:
            tar.extractall(paths.home)
