"""Check registry. Isolation checks are active adversarial tests, not permission inspections."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from core.certs import certs_present
from core.config import Settings, is_dev
from core.db import current_migration, migration_head
from core.gate.classify import classify
from core.paths import Paths, core_dir
from core.watch.killswitch import present as kill_present

PROBE_NAME = ".sabre-operator-probe"


def operator_probe_path() -> Path:
    return Path.home() / PROBE_NAME


def ensure_operator_probe() -> Path:
    """Regular file in the operator home. Directories cannot prove isolation."""
    path = operator_probe_path()
    if not path.exists():
        path.write_text("SABRE isolation probe\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _isolation_read(user: str, target: Path) -> bool:
    """Return True if the agent user CAN read target (bad), or the proof is incomplete."""
    if not target.is_file():
        # head(1) on a directory exits non-zero. That is not permission denied.
        return True
    if os.name == "nt" or is_dev() or not user:
        # Cannot prove isolation without a distinct OS user. Fail closed.
        return True
    try:
        r = subprocess.run(
            ["sudo", "-u", user, "head", "-c", "1", str(target)],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return True


def check_python(paths: Paths, settings: Settings):
    ok = sys.version_info >= (3, 11)
    return ok, f"Python {sys.version.split()[0]}"


def check_schema(paths: Paths, settings: Settings):
    if not paths.db.exists():
        return False, "database missing"
    return current_migration(paths.db) == migration_head(), f"schema {current_migration(paths.db)}"


def check_mtls(paths: Paths, settings: Settings):
    return certs_present(paths), "mTLS files present" if certs_present(paths) else "certs missing"


def check_inference(paths: Paths, settings: Settings):
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        key = bool(os.environ.get("SABRE_INFERENCE_KEY"))
        return key, "skipped live (key present)" if key else "SABRE_INFERENCE_KEY missing"
    from core.drivers.inference.openai_compat import OpenAICompatDriver

    try:
        d = OpenAICompatDriver()
        c = d.complete([{"role": "user", "content": "ping"}], "gpt-4.1-mini")
        d.usage("1970-01-01")
        return bool(c.text), "live completion ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def check_slack_auth(paths: Paths, settings: Settings):
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return bool(os.environ.get("SABRE_SLACK_BOT_TOKEN")), "skipped live"
    from core.drivers.messaging.slack import SlackDriver

    try:
        SlackDriver().auth_test()
        return True, "auth.test ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def check_slack_channels(paths: Paths, settings: Settings):
    needed = settings.channels or []
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return "skip", "channel membership not probed (SABRE_SKIP_LIVE)"
    import yaml

    ids = {}
    if paths.sabre_yaml.exists():
        cfg = yaml.safe_load(paths.sabre_yaml.read_text(encoding="utf-8")) or {}
        ids = dict(cfg.get("channel_ids") or {})
    missing = [n for n in needed if n not in ids]
    if missing:
        return False, f"missing channel ids: {', '.join(missing)}"
    from core.drivers.messaging.slack import SlackDriver

    try:
        driver = SlackDriver()
        absent = [n for n in needed if not driver.is_member(ids[n])]
    except Exception as exc:  # noqa: BLE001
        return False, f"membership unverified: {exc}"
    if absent:
        return False, f"bot not a member of: {', '.join(absent)}"
    return True, f"bot member of {len(needed)} channels"


def _iso(paths: Paths, settings: Settings, target: Path, label: str):
    user = settings.agent_user
    can = _isolation_read(user, target)
    if can:
        return False, f"agent user can read {label} (or isolation unproven)"
    return True, f"agent cannot read {label}"


def check_iso_home(paths: Paths, settings: Settings):
    return _iso(paths, settings, ensure_operator_probe(), "operator home")


def check_browser_profile(paths: Paths, settings: Settings):
    from core.runtime.browser import resolve_binary, validate_plan

    err = validate_plan(paths)
    if err:
        return False, err
    if not resolve_binary():
        return False, "no chromium-family browser on PATH"
    return True, f"launch --user-data-dir is {paths.browser_profile}"


def check_browser_cdp_url(paths: Paths, settings: Settings):
    """Fail if Hermes would attach to a Chrome SABRE does not own."""
    from core.runtime.hermes import hermes_home
    from core.runtime.hermes_browser import configured_cdp_url, is_sabre_owned_cdp

    cfg_path = hermes_home(paths) / "config.yaml"
    if not cfg_path.exists():
        return "skip", "hermes config.yaml not written"
    url = configured_cdp_url(paths)
    if is_sabre_owned_cdp(paths, url):
        return True, "browser.cdp_url unset" if not url else f"cdp_url is SABRE-owned ({url})"
    return False, f"browser.cdp_url points at a foreign endpoint: {url}"


def check_iso_browser(paths: Paths, settings: Settings):
    # Operator chrome/safari profile locations — prove agent cannot read them.
    candidates = [
        Path.home() / "Library/Application Support/Google/Chrome",
        Path.home() / ".config/google-chrome",
        Path.home() / "AppData/Local/Google/Chrome/User Data",
    ]
    target = next((c for c in candidates if c.exists()), Path.home())
    return _iso(paths, settings, target, "operator browser profile")


def check_iso_secrets(paths: Paths, settings: Settings):
    paths.secrets.mkdir(parents=True, exist_ok=True)
    if paths.proxy_key.exists():
        target = paths.proxy_key
    elif paths.proxy_store.exists():
        target = paths.proxy_store
    else:
        probe = paths.secrets / ".isolation-probe"
        if not probe.exists():
            probe.write_bytes(b"probe")
        target = probe
    return _iso(paths, settings, target, "credential store")


def check_iso_db(paths: Paths, settings: Settings):
    if not paths.db.exists():
        return False, "database missing"
    return _iso(paths, settings, paths.db, "database file")


def check_iso_core(paths: Paths, settings: Settings):
    probe = core_dir() / "__init__.py"
    if os.name == "nt" or is_dev():
        return False, "agent write to core/ unproven without OS user split"
    r = subprocess.run(
        ["sudo", "-u", settings.agent_user, "touch", str(probe) + ".probe"],
        capture_output=True,
        timeout=5,
    )
    leaked = r.returncode == 0
    Path(str(probe) + ".probe").unlink(missing_ok=True)
    if leaked:
        return False, "agent can write core/"
    return True, "agent cannot write core/"


def check_ceiling(paths: Paths, settings: Settings):
    spend = (settings.envelopes.get("spend") or {})
    per = float(spend.get("per_transaction_max") or 50)
    result = classify(
        {
            "kind": "spend",
            "payload": {"category": "domains", "amount_cents": int(per * 100) + 1},
            "idempotency_key": "doctor:ceiling",
            "rationale": "synthetic",
        },
        envelopes=settings.envelopes,
        no_spend=False,
    )
    msg = "over-ceiling refused" if result.classification == "red" else "ceiling not enforced"
    return result.classification == "red", msg


def check_unknown(paths: Paths, settings: Settings):
    result = classify(
        {"kind": "teleport", "payload": {}, "idempotency_key": "doctor:unknown", "rationale": "x"},
        envelopes=settings.envelopes,
        no_spend=True,
    )
    return result.classification == "red", "unknown kind is Red"


def check_kill(paths: Paths, settings: Settings):
    return kill_present(paths), "kill switch present" if kill_present(paths) else "run sabre setup --step 17"


def check_mem(paths: Paths, settings: Settings):
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        avail = 0
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) // 1024
                break
        ok = avail >= 512
        return ok, f"{avail} MB available"
    return "skip", "memory headroom not sampled on this host"


def check_sleep(paths: Paths, settings: Settings):
    if sys.platform == "darwin":
        try:
            custom = subprocess.run(["pmset", "-g", "custom"], capture_output=True, text=True, timeout=5)
            if custom.returncode != 0:
                return False, "pmset -g custom failed"
            ac_block = False
            sleep_ok = False
            disable_ok = False
            for line in custom.stdout.splitlines():
                if line.strip().startswith("AC Power"):
                    ac_block = True
                    continue
                if not ac_block:
                    continue
                if line.strip().startswith("Battery Power"):
                    break
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "sleep":
                    sleep_ok = parts[1] == "0"
                if len(parts) >= 2 and parts[0] == "disablesleep":
                    disable_ok = parts[1] == "1"
            if not ac_block:
                return False, "pmset AC Power block missing"
            ok = sleep_ok and disable_ok
            return ok, f"sleep={'0' if sleep_ok else '?'} disablesleep={'1' if disable_ok else '?'}"
        except Exception as exc:  # noqa: BLE001
            return False, f"pmset check failed: {exc}"
    if sys.platform.startswith("linux"):
        return "skip", "sleep assertion is macOS-only in Stage E"
    return "skip", "sleep assertion not verified on this host"


def check_disk(paths: Paths, settings: Settings):
    total, used, free = shutil.disk_usage(paths.home)
    ok = free > 2 * 1024 * 1024 * 1024
    return ok, f"{free // (1024**3)} GB free"


def check_backup(paths: Paths, settings: Settings):
    backups = list(paths.backups.glob("*.tar.gz")) if paths.backups.exists() else []
    return bool(backups), "backup present" if backups else "no backup yet (sabre backup)"


def check_optional(paths: Paths, settings: Settings):
    missing = [s for s in ("cards", "payments", "hosting") if not settings.driver_enabled(s)]
    if missing:
        return False, f"{', '.join(missing)} not configured (no-spend/degraded)"
    return True, "optional providers configured"


def check_alert_fallback(paths: Paths, settings: Settings):
    cards = settings.raw.get("drivers", {}).get("cards", {})
    payments = settings.raw.get("drivers", {}).get("payments", {})
    money_on = bool(cards.get("enabled")) or bool(payments.get("enabled"))
    if not money_on:
        return True, "money drivers disabled"
    fb = (settings.raw.get("alerts") or {}).get("fallback") or {}
    name = fb.get("name") or os.environ.get("SABRE_ALERT_FALLBACK_DRIVER") or ""
    if not name:
        return False, "cards/payments enabled but alerts.fallback.name missing"
    to = fb.get("to") or os.environ.get("SABRE_ALERT_EMAIL_TO") or ""
    if not to:
        return False, "alerts.fallback.to missing"
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return True, f"skipped live ({name} configured)"
    try:
        from core.drivers.loader import load_driver

        kwargs = {k: v for k, v in fb.items() if k not in {"name", "to", "enabled"}}
        if name == "memory":
            kwargs.setdefault("path", paths.runtime / ".alert-doctor-probe.jsonl")
        driver = load_driver("alerts", name, **kwargs)
        driver.send(to, "SABRE doctor probe", "alert fallback reachability probe")
        return True, f"fallback {name} reachable"
    except Exception as exc:
        return False, str(exc)


def check_mirror(paths: Paths, settings: Settings):
    url = os.environ.get("SABRE_MIRROR_URL")
    if not url:
        return False, "mirror not configured"
    return True, url


def _luhn_valid(digits: str) -> bool:
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    rev = digits[::-1]
    for i, ch in enumerate(rev):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _agent_readable_roots(paths: Paths) -> list[Path]:
    return [paths.work, paths.runtime, paths.logs, paths.config_dir, paths.app]


def _scan_text_for_pans(text: str) -> list[str]:
    hits: list[str] = []
    for match in re.finditer(r"\d{13,19}", text):
        candidate = match.group(0)
        if _luhn_valid(candidate):
            hits.append(candidate)
    return hits


def check_pan_leak(paths: Paths, settings: Settings):
    hits: list[str] = []
    for root in _agent_readable_roots(paths):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".db", ".sqlite"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pan in _scan_text_for_pans(text):
                hits.append(f"{path.relative_to(paths.home)}:{pan[:6]}…")
    if hits:
        return False, f"Luhn-valid PAN in agent-readable tree: {', '.join(hits[:3])}"
    return True, "no PAN-shaped secrets in agent-readable paths"


def check_review_configured(paths: Paths, settings: Settings):
    cards = settings.raw.get("drivers", {}).get("cards", {})
    payments = settings.raw.get("drivers", {}).get("payments", {})
    money_on = settings.driver_enabled("cards") or settings.driver_enabled("payments")
    if not money_on:
        return True, "money drivers disabled"
    review_key = os.environ.get("SABRE_REVIEW_KEY") or ""
    if not review_key:
        return False, "drivers.cards/payments enabled but SABRE_REVIEW_KEY missing"
    review_base = os.environ.get("SABRE_REVIEW_BASE_URL") or ""
    core_base = os.environ.get("SABRE_INFERENCE_BASE_URL") or ""
    infer_key = os.environ.get("SABRE_INFERENCE_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if review_base and core_base and review_base.rstrip("/") == core_base.rstrip("/") and review_key == infer_key:
        return False, "review provider must differ from core inference provider"
    if os.environ.get("SABRE_SKIP_LIVE") == "1":
        return True, "skipped live (review key present)"
    return True, "adversarial review configured"


def check_reconcile(paths: Paths, settings: Settings):
    report = paths.home / "reconcile-last.json"
    if not report.exists():
        return "skip", "no reconciliation has run yet"
    import json

    data = json.loads(report.read_text(encoding="utf-8"))
    divergences = data.get("divergences") or []
    if divergences:
        return False, f"{len(divergences)} divergences"
    if not data.get("ok"):
        return False, str(data.get("reason") or "reconcile not clean")
    return True, "last reconciliation clean"


def check_personas(paths: Paths, settings: Settings):
    dest = paths.home / "personas"
    n = len(list(dest.glob("*.md"))) if dest.exists() else 0
    n += len(list((core_dir() / "runtime" / "personas").glob("*.md")))
    return n > 0, f"{n} persona files"


def check_hermes_schema(paths: Paths, settings: Settings):
    """Fail if SABRE wrote a key Hermes v0.20.1 does not recognise."""
    from core.runtime.hermes import hermes_home
    from core.runtime.hermes_schema import unknown_written_keys

    cfg_path = hermes_home(paths) / "config.yaml"
    if not cfg_path.exists():
        return "skip", "hermes config.yaml not written"
    try:
        import yaml

        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return False, f"hermes config unreadable: {exc}"
    if not isinstance(data, dict):
        return False, "hermes config.yaml is not a mapping"
    unknown = unknown_written_keys(data)
    if unknown:
        return False, "unrecognized hermes keys: " + ", ".join(unknown)
    return True, "all written keys are in the Hermes v0.20.1 schema"


def check_hermes_version(paths: Paths, settings: Settings):
    """Fail if the installed Hermes version drifted from the vendored schema."""
    from core.runtime.hermes_schema import HERMES_VERSION, installed_hermes_version

    found = installed_hermes_version()
    if not found:
        return "skip", "installed Hermes version unreadable"
    if found != HERMES_VERSION:
        return False, (
            f"installed Hermes {found} != vendored schema {HERMES_VERSION}; "
            "re-run the schema audit"
        )
    return True, f"Hermes {found} matches vendored schema"


def check_hermes_jobs(paths: Paths, settings: Settings):
    """Fail if cron/jobs.json is missing, malformed, or missing a SABRE job."""
    import json

    from core.runtime.hermes import hermes_home
    from core.runtime.hermes_jobs import (
        EXPECTED_JOB_NAMES,
        jobs_path,
        missing_expected_jobs,
        validate_jobs_document,
    )

    home = hermes_home(paths)
    cfg_path = home / "config.yaml"
    dest = jobs_path(home)
    if not cfg_path.exists() and not dest.exists():
        return "skip", "hermes layout not written"
    if not dest.exists():
        return False, "HERMES_HOME/cron/jobs.json missing"
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, f"jobs.json unreadable: {exc}"
    errors = validate_jobs_document(data)
    if errors:
        return False, "jobs.json malformed: " + "; ".join(errors[:8])
    missing = missing_expected_jobs(data)
    if missing:
        return False, "missing SABRE jobs: " + ", ".join(missing)
    scripts_dir = home / "scripts"
    expected = set(EXPECTED_JOB_NAMES)
    absent = [
        str(job["script"])
        for job in data.get("jobs") or []
        if isinstance(job, dict)
        and job.get("name") in expected
        and job.get("script")
        and not (scripts_dir / str(job["script"])).is_file()
    ]
    if absent:
        return False, "missing cron scripts: " + ", ".join(absent)
    n = len(data.get("jobs") or [])
    return True, f"{n} jobs in HERMES_HOME/cron/jobs.json"


def check_hermes_cron_list(paths: Paths, settings: Settings):
    """Fail if config.yaml repeats the Stage A bug: cron as a job list."""
    from core.runtime.hermes import hermes_home

    cfg_path = hermes_home(paths) / "config.yaml"
    if not cfg_path.exists():
        return "skip", "hermes config.yaml not written"
    try:
        import yaml

        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return False, f"hermes config unreadable: {exc}"
    if not isinstance(data, dict):
        return False, "hermes config.yaml is not a mapping"
    cron = data.get("cron")
    if isinstance(cron, list):
        return False, "config.yaml cron: is a list; jobs belong in cron/jobs.json"
    return True, "config.yaml cron is not a job list"


def check_hermes(paths: Paths, settings: Settings):
    from core.runtime.hermes import hermes_home, resolve_hermes_bin

    bin_path = resolve_hermes_bin()
    if not bin_path:
        return False, "hermes binary not on PATH"
    cfg = hermes_home(paths) / "config.yaml"
    if not cfg.exists():
        return False, "hermes config.yaml not written"
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return False, f"hermes config unreadable: {exc}"
    mcp = data.get("mcp_servers") or {}
    if "sabre-gate" not in mcp:
        return False, "hermes config missing sabre-gate MCP"
    hooks = (data.get("hooks") or {}).get("post_tool_call") or []
    if not hooks:
        return False, "hermes config missing post_tool_call tap"
    return True, bin_path


def fix_hermes(paths: Paths, settings: Settings) -> None:
    from core.runtime.hermes import write_hermes_layout

    write_hermes_layout(paths, settings)


def all_checks() -> list[dict]:
    return [
        {"id": "env.python", "severity": "fatal", "run": check_python, "remedy": "install Python 3.11"},
        {"id": "db.schema", "severity": "fatal", "run": check_schema, "remedy": "sabre setup --step 3"},
        {"id": "certs.mtls", "severity": "fatal", "run": check_mtls, "remedy": "sabre setup --step 4"},
        {"id": "inference.live", "severity": "fatal", "run": check_inference, "remedy": "sabre setup --step 5"},
        {"id": "slack.auth", "severity": "fatal", "run": check_slack_auth, "remedy": "sabre setup --step 6"},
        {"id": "slack.channels", "severity": "fatal", "run": check_slack_channels, "remedy": "sabre setup --step 8"},
        {"id": "isolation.home", "severity": "fatal", "run": check_iso_home, "remedy": "sabre setup --step 2"},
        {"id": "isolation.browser", "severity": "fatal", "run": check_iso_browser, "remedy": "sabre setup --step 2"},
        {"id": "isolation.secrets", "severity": "fatal", "run": check_iso_secrets, "remedy": "sabre setup --step 2"},
        {"id": "isolation.db", "severity": "fatal", "run": check_iso_db, "remedy": "sabre setup --step 2"},
        {"id": "isolation.core", "severity": "fatal", "run": check_iso_core, "remedy": "sabre setup --step 2"},
        {"id": "gate.ceiling", "severity": "fatal", "run": check_ceiling, "remedy": "sabre setup --step 9"},
        {"id": "gate.unknown", "severity": "fatal", "run": check_unknown, "remedy": "check core/gate/classify.py"},
        {
            "id": "alerts.fallback",
            "severity": "fatal",
            "run": check_alert_fallback,
            "remedy": "configure alerts.fallback (smtp or memory) when cards/payments are enabled",
        },
        {
            "id": "review.configured",
            "severity": "fatal",
            "run": check_review_configured,
            "remedy": "set SABRE_REVIEW_KEY on a different provider than core when cards/payments are enabled",
        },
        {
            "id": "secrets.pan_leak",
            "severity": "fatal",
            "run": check_pan_leak,
            "remedy": "move PAN/CVV to gate credential store; remove from runtime/ and work/",
        },
        {"id": "killswitch", "severity": "fatal", "run": check_kill, "remedy": "sabre setup --step 17"},
        {
            "id": "browser.profile",
            "severity": "fatal",
            "run": check_browser_profile,
            "remedy": "sabre setup --step 13",
        },
        {
            "id": "browser.cdp_url",
            "severity": "fatal",
            "run": check_browser_cdp_url,
            "fix": fix_hermes,
            "remedy": "unset browser.cdp_url and BROWSER_CDP_URL; never attach the operator's Chrome",
        },
        {"id": "mem.headroom", "severity": "warning", "run": check_mem, "remedy": "free RAM or reduce concurrency"},
        {"id": "disk.free", "severity": "warning", "run": check_disk, "remedy": "free disk"},
        {"id": "sleep.disabled", "severity": "warning", "run": check_sleep, "remedy": "disable sleep on power"},
        {"id": "backup.recent", "severity": "warning", "run": check_backup, "remedy": "sabre backup"},
        {"id": "providers.optional", "severity": "warning", "run": check_optional, "remedy": "sabre setup --step 10"},
        {"id": "mirror.reachable", "severity": "warning", "run": check_mirror, "remedy": "sabre setup --step 15"},
        {
            "id": "reconcile.clean",
            "severity": "warning",
            "run": check_reconcile,
            "remedy": "resolve provider divergence before spending",
        },
        {"id": "personas.synced", "severity": "warning", "run": check_personas, "remedy": "sabre personas sync"},
        {
            "id": "runtime.hermes",
            "severity": "fatal",
            "run": check_hermes,
            "fix": fix_hermes,
            "remedy": "install.sh or set SABRE_HERMES_BIN; start sabre-agent once to write config",
        },
        {
            "id": "runtime.hermes.schema",
            "severity": "fatal",
            "run": check_hermes_schema,
            "fix": fix_hermes,
            "remedy": "remove keys Hermes does not read; rewrite with sabre-agent or write_hermes_layout",
        },
        {
            "id": "runtime.hermes.version",
            "severity": "fatal",
            "run": check_hermes_version,
            "remedy": "re-run the schema audit; vendor the installed Hermes config and jobs schemas",
        },
        {
            "id": "runtime.hermes.jobs",
            "severity": "fatal",
            "run": check_hermes_jobs,
            "fix": fix_hermes,
            "remedy": "sabre-agent or write_hermes_layout to write HERMES_HOME/cron/jobs.json",
        },
        {
            "id": "runtime.hermes.cron-list",
            "severity": "fatal",
            "run": check_hermes_cron_list,
            "fix": fix_hermes,
            "remedy": "remove the cron job list from config.yaml; jobs belong in cron/jobs.json",
        },
    ]
