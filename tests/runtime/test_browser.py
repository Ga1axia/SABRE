from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from core.config import load_settings
from core.runtime.browser import (
    cookie_count,
    launch_argv,
    load_page,
    user_data_dir_from_argv,
    validate_plan,
    write_launch_plan,
)
from core.setup.checks import check_browser_profile

MARKER = "SABRE-BROWSER-PROBE-OK"


def test_launch_argv_binds_isolated_profile(sabre_home):
    argv = launch_argv(sabre_home)
    udd = user_data_dir_from_argv(argv)
    assert udd is not None
    assert udd.resolve() == sabre_home.browser_profile.resolve()
    flag = next(a for a in argv if a.startswith("--user-data-dir"))
    assert str(sabre_home.browser_profile.resolve()) in flag
    operator = Path.home() / "AppData/Local/Google/Chrome/User Data"
    assert udd.resolve() != operator.resolve()


def test_doctor_fails_if_user_data_dir_points_elsewhere(sabre_home, tmp_path):
    wrong = tmp_path / "operator-chrome"
    wrong.mkdir()
    write_launch_plan(sabre_home, ["chrome", f"--user-data-dir={wrong}"])
    ok, msg = check_browser_profile(sabre_home, load_settings(sabre_home))
    assert ok is False
    assert "user-data-dir" in msg.lower() or "points" in msg.lower()


def test_validate_plan_accepts_bound_profile(sabre_home):
    write_launch_plan(sabre_home, launch_argv(sabre_home))
    assert validate_plan(sabre_home) is None


def test_cookie_jar_starts_empty_and_separate(sabre_home):
    sabre_home.browser_profile.mkdir(parents=True, exist_ok=True)
    assert cookie_count(sabre_home.browser_profile) == 0
    operator = Path.home() / "AppData/Local/Google/Chrome/User Data"
    assert sabre_home.browser_profile.resolve() != operator.resolve()
    assert operator.resolve() not in sabre_home.browser_profile.resolve().parents


def _serve_marker():
    html = f"<html><body><p>{MARKER}</p></body></html>".encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_load_page_reports_content_from_isolated_profile(sabre_home):
    httpd = _serve_marker()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    try:
        result = load_page(sabre_home, url)
        assert MARKER in result["content"]
        assert result["url"] == url
        udd = user_data_dir_from_argv(result["argv"])
        assert udd.resolve() == sabre_home.browser_profile.resolve()
        assert cookie_count(sabre_home.browser_profile) == 0
        plan = json.loads((sabre_home.runtime / "browser-launch.json").read_text(encoding="utf-8"))
        planned = user_data_dir_from_argv(plan["argv"])
        assert planned.resolve() == sabre_home.browser_profile.resolve()
    finally:
        httpd.shutdown()
