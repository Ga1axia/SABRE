from __future__ import annotations

from core.services.backup import create_backup, restore_backup


def test_backup_roundtrip(sabre_home):
    (sabre_home.work / "COMPANY.md").write_text("# Identity\n", encoding="utf-8")
    dest = create_backup(sabre_home)
    assert dest.exists()
    restore_backup(sabre_home, str(dest), dry_run=True)
    restore_backup(sabre_home, str(dest), dry_run=False)
    company = sabre_home.work / "COMPANY.md"
    assert company.exists() or (sabre_home.home / "work" / "COMPANY.md").exists()
