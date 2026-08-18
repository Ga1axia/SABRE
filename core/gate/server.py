"""I1 HTTPS JSON API. Agent is the only client. Gate never calls the agent."""

from __future__ import annotations

import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.config import Settings, load_settings
from core.db import connect, utcnow
from core.drivers.inference.pricing import estimate_cost_cents
from core.errors import classify
from core.gate.ledger import claim_task
from core.gate.loop import (
    concurrent_ventures,
    kill_sweep,
    promote,
    record_skill_venture,
    venture_net_cents,
)
from core.gate.loop import tick as loop_tick
from core.gate.reconcile import reconcile
from core.gate.review import review_intent
from core.gate.submit import effect_drivers, submit_intent
from core.ids import new_id
from core.paths import Paths, default_home
from core.watch import alert as watch_alert
from core.watch.killswitch import is_killed


def _maybe_alert_unknown_cost(paths: Paths, cost: int | None, tin: int, tout: int, *, model: str, tool: str) -> None:
    if cost is not None:
        return
    if int(tin or 0) <= 0 and int(tout or 0) <= 0:
        return
    watch_alert.alert_once(
        paths,
        f"unknown-cost:{tool}:{model or 'unknown'}",
        (
            f"unknown inference cost: {tin} in / {tout} out tokens for {model or 'unknown'} "
            f"(tool={tool}); recorded NULL"
        ),
    )


def _json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    n = int(handler.headers.get("Content-Length") or 0)
    if not n:
        return {}
    raw = handler.rfile.read(n)
    return json.loads(raw.decode("utf-8") or "{}")


def http_for(exc: BaseException) -> tuple[int, dict[str, Any]]:
    err = classify(exc)
    if err.kind == "retryable":
        return 503, {"error": str(err), "class": "retryable"}
    if err.kind == "escalate":
        return 422, {"error": str(err), "class": "escalate"}
    return 500, {"error": str(err), "class": "bug"}


def make_handler(settings: Settings):
    paths = settings.paths

    class GateHandler(BaseHTTPRequestHandler):
        server_version = "sabre-gate/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            (paths.logs / "gate.jsonl").parent.mkdir(parents=True, exist_ok=True)
            with (paths.logs / "gate.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"msg": fmt % args, "at": utcnow()}) + "\n")

        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            self._guarded(lambda: self._route("GET", urlparse(self.path)))

        def do_POST(self) -> None:  # noqa: N802
            self._guarded(lambda: self._route("POST", urlparse(self.path)))

        def do_PATCH(self) -> None:  # noqa: N802
            self._guarded(lambda: self._route("PATCH", urlparse(self.path)))

        def _guarded(self, fn) -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                code, body = http_for(exc)
                if body["class"] in {"bug", "escalate"}:
                    try:
                        from core.watch.alert import alert_once

                        chan = "requests" if body["class"] == "escalate" else "status"
                        alert_once(
                            paths,
                            f"gate:{body['class']}:{body['error'][:80]}",
                            f"gate {body['class']}: {body['error']}",
                            chan,
                        )
                    except Exception:
                        pass
                self._send(code, body)

        def _route(self, method: str, parsed) -> None:
            path = parsed.path.rstrip("/") or "/"
            if path == "/v1/health" and method == "GET":
                self._send(200, {"ok": True, "kill": is_killed(paths)})
                return
            conn = connect(paths.db)
            try:
                if path == "/v1/heartbeat" and method == "POST":
                    body = _json_body(self)
                    svc = str(body.get("service") or "agent")
                    conn.execute("INSERT INTO heartbeats(service, at) VALUES (?, ?)", (svc, utcnow()))
                    conn.commit()
                    self._send(200, {"ok": True})
                    return
                if path == "/v1/intents" and method == "POST":
                    self._send(200, submit_intent(settings, conn, _json_body(self)))
                    conn.commit()
                    return
                if path.startswith("/v1/intents/") and method == "GET":
                    iid = path.rsplit("/", 1)[-1]
                    row = conn.execute("SELECT * FROM intents WHERE id=?", (iid,)).fetchone()
                    if not row:
                        self._send(404, {"error": "not found"})
                        return
                    self._send(200, dict(row))
                    return
                if path == "/v1/intents" and method == "GET":
                    qs = parse_qs(parsed.query)
                    sql = "SELECT * FROM intents WHERE 1=1"
                    args: list[Any] = []
                    if qs.get("state"):
                        sql += " AND state=?"
                        args.append(qs["state"][0])
                    if qs.get("venture"):
                        sql += " AND venture_id=?"
                        args.append(qs["venture"][0])
                    rows = [dict(r) for r in conn.execute(sql, args)]
                    self._send(200, {"intents": rows})
                    return
                if path == "/v1/ledger/ventures" and method == "GET":
                    rows = [dict(r) for r in conn.execute("SELECT * FROM ventures")]
                    self._send(200, {"ventures": rows})
                    return
                if path == "/v1/ledger/ventures" and method == "POST":
                    body = _json_body(self)
                    max_v = int((settings.envelopes.get("portfolio") or {}).get("max_concurrent_ventures") or 3)
                    if concurrent_ventures(conn) >= max_v:
                        self._send(409, {"error": "portfolio full; kill a venture first"})
                        return
                    dissent = review_intent(
                        settings,
                        {"kind": "venture_launch", "rationale": body.get("thesis") or "", "payload": body},
                        "red",
                    )
                    vid = new_id("V")
                    conn.execute(
                        """INSERT INTO ventures(id, slug, name, thesis, icp, status, kill_criteria, created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            vid,
                            body["slug"],
                            body.get("name") or body["slug"],
                            body.get("thesis") or "",
                            body.get("icp"),
                            body.get("status") or "ideating",
                            json.dumps(
                                body.get("kill_criteria")
                                or {"no_revenue_spend_cents": 15000, "no_revenue_days": 21}
                            ),
                            utcnow(),
                        ),
                    )
                    conn.commit()
                    self._send(200, {"id": vid, "slug": body["slug"], "dissent": dissent})
                    return
                if path.startswith("/v1/ledger/ventures/") and method == "PATCH":
                    slug = path.rsplit("/", 1)[-1]
                    body = _json_body(self)
                    allowed = {k: body[k] for k in ("status", "thesis", "icp", "name") if k in body}
                    if not allowed:
                        self._send(400, {"error": "no updatable fields"})
                        return
                    sets = ", ".join(f"{k}=?" for k in allowed)
                    conn.execute(f"UPDATE ventures SET {sets} WHERE slug=?", [*allowed.values(), slug])
                    conn.commit()
                    self._send(200, {"ok": True})
                    return
                if path == "/v1/ledger/transactions" and method == "GET":
                    q = "SELECT * FROM transactions ORDER BY occurred_at DESC LIMIT 200"
                    rows = [dict(r) for r in conn.execute(q)]
                    self._send(200, {"transactions": rows})
                    return
                if path == "/v1/ledger/envelopes" and method == "GET":
                    self._send(200, {"envelopes": settings.envelopes, "no_spend": settings.no_spend})
                    return
                if path == "/v1/tasks" and method == "POST":
                    body = _json_body(self)
                    tid = body.get("id") or new_id("T")
                    if not body.get("acceptance"):
                        self._send(400, {"error": "acceptance criteria required"})
                        return
                    conn.execute(
                        """INSERT INTO tasks(id, venture_id, parent_id, goal, acceptance, team, status, created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            tid,
                            body.get("venture_id"),
                            body.get("parent_id"),
                            body["goal"],
                            body["acceptance"],
                            json.dumps(body.get("team") or []),
                            "ready",
                            utcnow(),
                        ),
                    )
                    conn.commit()
                    self._send(200, {"id": tid})
                    return
                if path.startswith("/v1/tasks/") and path.endswith("/claim") and method == "POST":
                    tid = path.split("/")[3]
                    body = _json_body(self)
                    actor = body.get("actor") or "core"
                    if not claim_task(conn, tid, actor, settings.task_lease_seconds):
                        self._send(409, {"error": "not claimable"})
                        return
                    conn.commit()
                    self._send(200, {"id": tid, "claimed_by": actor})
                    return
                if path.startswith("/v1/tasks/") and path.endswith("/release") and method == "POST":
                    tid = path.split("/")[3]
                    conn.execute("UPDATE tasks SET claimed_by=NULL, status='ready' WHERE id=?", (tid,))
                    conn.commit()
                    self._send(200, {"ok": True})
                    return
                if path.startswith("/v1/tasks/") and method == "PATCH":
                    tid = path.rsplit("/", 1)[-1]
                    body = _json_body(self)
                    allowed = {k: body[k] for k in ("status", "result", "goal") if k in body}
                    if "acceptance" in body and not body["acceptance"]:
                        self._send(400, {"error": "acceptance cannot be empty"})
                        return
                    if "acceptance" in body:
                        allowed["acceptance"] = body["acceptance"]
                    sets = ", ".join(f"{k}=?" for k in allowed)
                    conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", [*allowed.values(), tid])
                    conn.commit()
                    self._send(200, {"ok": True})
                    return
                if path == "/v1/lessons" and method == "POST":
                    body = _json_body(self)
                    lid = new_id("L")
                    conn.execute(
                        """INSERT INTO lessons(id, venture_id, context, expected, happened, rule, status, created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            lid,
                            body.get("venture_id"),
                            body.get("context") or "",
                            body.get("expected") or "",
                            body.get("happened") or "",
                            body.get("rule") or "",
                            "candidate",
                            utcnow(),
                        ),
                    )
                    conn.commit()
                    self._send(200, {"id": lid, "status": "candidate"})
                    return
                if path == "/v1/postmortems" and method == "POST":
                    body = _json_body(self)
                    pid = new_id("PM")
                    conn.execute(
                        """INSERT INTO postmortems(id, venture_id, believed, did, happened, earliest_signal, created_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            pid,
                            body.get("venture_id"),
                            body.get("believed") or "",
                            body.get("did") or "",
                            body.get("happened") or "",
                            body.get("earliest_signal"),
                            utcnow(),
                        ),
                    )
                    conn.commit()
                    self._send(200, {"id": pid})
                    return
                if path.startswith("/v1/skills/") and path.endswith("/record-use") and method == "POST":
                    sid = path.split("/")[3]
                    body = _json_body(self)
                    tin = int(body.get("tokens_in") or 0)
                    tout = int(body.get("tokens_out") or 0)
                    model = str(body.get("model") or "")
                    cost = estimate_cost_cents(model, tin, tout)
                    _maybe_alert_unknown_cost(paths, cost, tin, tout, model=model, tool=f"skill:{sid}")
                    if cost is None:
                        conn.execute("UPDATE skills SET uses=uses+1 WHERE id=?", (sid,))
                    else:
                        conn.execute(
                            "UPDATE skills SET uses=uses+1, net_cents=net_cents-? WHERE id=?",
                            (cost, sid),
                        )
                    vid = str(body.get("venture_id") or "")
                    if vid:
                        record_skill_venture(paths, sid, vid, venture_net_cents(conn, vid))
                    conn.commit()
                    self._send(200, {"ok": True, "cost_cents": cost})
                    return
                if path == "/v1/skills" and method == "GET":
                    rows = [dict(r) for r in conn.execute("SELECT * FROM skills")]
                    self._send(200, {"skills": rows})
                    return
                if path == "/v1/skills" and method == "POST":
                    body = _json_body(self)
                    sid = new_id("SK")
                    conn.execute(
                        """INSERT INTO skills(id, name, status, uses, net_cents, created_at)
                           VALUES (?,?,?,?,?,?)""",
                        (sid, body.get("name") or sid, "candidate", 0, 0, utcnow()),
                    )
                    conn.commit()
                    self._send(200, {"id": sid, "status": "candidate"})
                    return
                if path == "/v1/loop/tick" and method == "POST":
                    result = loop_tick(settings, conn, _json_body(self))
                    conn.commit()
                    self._send(200, result)
                    return
                if path == "/v1/loop/kill-sweep" and method == "POST":
                    result = kill_sweep(settings, conn)
                    conn.commit()
                    self._send(200, result)
                    return
                if path == "/v1/loop/promote" and method == "POST":
                    result = promote(settings, conn)
                    conn.commit()
                    self._send(200, result)
                    return
                if path == "/v1/loop/reconcile" and method == "POST":
                    result = reconcile(effect_drivers(settings), conn, paths=paths)
                    conn.commit()
                    self._send(200, result)
                    return
                if path == "/v1/accounts" and method == "GET":
                    q = "SELECT id, platform, handle, owner, status, created_at FROM accounts"
                    rows = [dict(r) for r in conn.execute(q)]
                    self._send(200, {"accounts": rows})
                    return
                if path == "/v1/events" and method == "POST":
                    body = _json_body(self)
                    tin = int(body.get("tokens_in") or 0)
                    tout = int(body.get("tokens_out") or 0)
                    model = str(body.get("model") or "")
                    cost = estimate_cost_cents(model, tin, tout)
                    _maybe_alert_unknown_cost(
                        paths, cost, tin, tout, model=model, tool=str(body.get("tool") or "event")
                    )
                    conn.execute(
                        """INSERT INTO events(
                               trace_id, venture_id, session_id, actor, tool, args,
                               status, duration_ms, tokens_in, tokens_out, cost_cents, occurred_at
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            body.get("trace_id"),
                            body.get("venture_id"),
                            body.get("session_id"),
                            body.get("actor") or "core",
                            body.get("tool"),
                            body.get("args"),
                            body.get("status"),
                            body.get("duration_ms"),
                            tin,
                            tout,
                            cost,
                            utcnow(),
                        ),
                    )
                    conn.commit()
                    self._send(200, {"ok": True, "cost_cents": cost})
                    return
                self._send(404, {"error": "not an agent endpoint"})
            finally:
                conn.close()

    return GateHandler


def serve(settings: Settings | None = None) -> None:
    settings = settings or load_settings(Paths(default_home()))
    host = "127.0.0.1"
    port = int((settings.raw.get("paths") or {}).get("gate_port") or 8788)
    httpd = ThreadingHTTPServer((host, port), make_handler(settings))
    insecure = os.environ.get("SABRE_GATE_INSECURE", "").strip() in {"1", "true"}
    certs = settings.paths.certs
    if not insecure and (certs / "gate.crt").exists():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certs / "gate.crt", certs / "gate.key")
        ctx.load_verify_locations(certs / "ca.crt")
        ctx.verify_mode = ssl.CERT_REQUIRED
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"sabre-gate listening on {host}:{port}")
    import threading
    import time

    from core.watch.heartbeat import beat

    def _beats() -> None:
        while True:
            try:
                beat(settings.paths, "gate")
            except Exception:
                pass
            time.sleep(int(settings.raw.get("heartbeat_seconds") or 300))

    threading.Thread(target=_beats, daemon=True).start()
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
