"""SMTP alert delivery. Uses smtplib directly — not core.net and not the Slack circuit."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from core.errors import SabreError


class SmtpAlertDriver:
    name = "smtp"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        use_tls: bool | None = None,
        **_: Any,
    ):
        self.host = host or os.environ.get("SABRE_ALERT_SMTP_HOST") or ""
        self.port = int(port if port is not None else os.environ.get("SABRE_ALERT_SMTP_PORT") or 587)
        self.user = user or os.environ.get("SABRE_ALERT_SMTP_USER") or ""
        self.password = password or os.environ.get("SABRE_ALERT_SMTP_PASSWORD") or ""
        if use_tls is None:
            raw = os.environ.get("SABRE_ALERT_SMTP_TLS", "1")
            self.use_tls = raw.strip().lower() not in {"0", "false", "no"}
        else:
            self.use_tls = bool(use_tls)

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.host:
            raise SabreError("SMTP host missing", remedy="set SABRE_ALERT_SMTP_HOST or alerts.fallback.host")
        if not to:
            raise SabreError("alert recipient missing", remedy="set alerts.fallback.to or SABRE_ALERT_EMAIL_TO")
        msg = EmailMessage()
        msg["Subject"] = subject[:200]
        msg["From"] = self.user or "sabre@localhost"
        msg["To"] = to
        msg.set_content(body[:8000])
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)
