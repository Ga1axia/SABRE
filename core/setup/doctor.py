"""Doctor: registered checks with id, severity, run(), remedy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.config import load_settings
from core.paths import Paths
from core.setup.checks import all_checks

Severity = Literal["fatal", "warning", "skip"]


@dataclass
class CheckResult:
    id: str
    severity: Severity
    ok: bool
    message: str
    remedy: str = ""

    @property
    def skipped(self) -> bool:
        return self.severity == "skip"


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok or r.severity != "fatal" for r in self.results)

    def blocking_fatals(self, *, waive_isolation: bool = False) -> list[CheckResult]:
        out = []
        for r in self.results:
            if r.severity != "fatal" or r.ok or r.skipped:
                continue
            if waive_isolation and r.id.startswith("isolation."):
                continue
            out.append(r)
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [r.__dict__ | {"skipped": r.skipped} for r in self.results],
        }

    def format(self) -> str:
        lines = []
        fatals = [r for r in self.results if r.severity == "fatal"]
        warns = [r for r in self.results if r.severity == "warning"]
        skips = [r for r in self.results if r.severity == "skip"]
        for r in fatals:
            mark = "✓" if r.ok else "✗"
            lines.append(f"  {mark} {r.id} — {r.message}")
            if not r.ok and r.remedy:
                lines.append(f"      → {r.remedy}")
        for r in warns:
            mark = "✓" if r.ok else "⚠"
            lines.append(f"  {mark} {r.id} — {r.message}")
            if not r.ok and r.remedy:
                lines.append(f"      → {r.remedy}")
        for r in skips:
            lines.append(f"  – {r.id} — skipped: {r.message}")
        passed = sum(1 for r in fatals if r.ok)
        lines.append(f"  {'Ready.' if self.ok else 'Not ready.'} {passed}/{len(fatals)} fatal checks passed")
        return "\n".join(lines)


def run_doctor(paths: Paths, fix: bool = False) -> Report:
    settings = load_settings(paths)
    report = Report()
    for check in all_checks():
        if fix and check.get("fix"):
            try:
                check["fix"](paths, settings)
            except Exception:
                pass
        try:
            status, message = check["run"](paths, settings)
        except Exception as exc:  # noqa: BLE001
            status, message = False, str(exc)
        if status == "skip":
            report.results.append(
                CheckResult(
                    id=check["id"],
                    severity="skip",
                    ok=False,
                    message=message,
                    remedy=check.get("remedy") or "",
                )
            )
            continue
        report.results.append(
            CheckResult(
                id=check["id"],
                severity=check["severity"],
                ok=bool(status),
                message=message,
                remedy=check.get("remedy") or "",
            )
        )
    return report
