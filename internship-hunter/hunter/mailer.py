"""Sends applications by SMTP with the safety rails that keep your mailbox out of spam
folders: a daily cap, a pause between emails, one email per company, and an opt-out list.
Dry-run (the default) writes .eml files to outbox/ instead of sending."""
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .contacts import domain_of


def build(cfg, to: str, subject: str, body: str, attachments: list[Path]) -> EmailMessage:
    p = cfg.profile
    msg = EmailMessage()
    msg["From"] = f'{p.get("name", "")} <{cfg.email.get("smtp_user") or p.get("email")}>'
    msg["To"] = to
    msg["Reply-To"] = p.get("email", "")
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain_of(p.get("email", "local@localhost")) or None)
    msg["List-Unsubscribe"] = f"<mailto:{p.get('email', '')}?subject=unsubscribe>"
    footer = ("\n\n--\nIf you would rather not receive applications at this address, reply "
              "\"unsubscribe\" and I will not write again.")
    msg.set_content(body + footer)
    for a in attachments:
        if a and a.exists():
            msg.add_attachment(a.read_bytes(), maintype="application", subtype="pdf", filename=a.name)
    return msg


class Sender:
    def __init__(self, cfg, db, live: bool):
        self.cfg, self.db, self.live = cfg, db, live
        self.smtp = None
        self.last = 0.0

    def __enter__(self):
        if self.live:
            e = self.cfg.email
            password = self.cfg.secret("SMTP_PASSWORD")
            if not password:
                raise SystemExit("Set SMTP_PASSWORD (an app password) to send for real.")
            port = int(e.get("smtp_port", 465))
            if port == 465:
                self.smtp = smtplib.SMTP_SSL(e["smtp_host"], port, context=ssl.create_default_context(), timeout=30)
            else:
                self.smtp = smtplib.SMTP(e["smtp_host"], port, timeout=30)
                self.smtp.starttls(context=ssl.create_default_context())
            self.smtp.login(e.get("smtp_user") or self.cfg.profile["email"], password)
        return self

    def __exit__(self, *exc):
        if self.smtp:
            self.smtp.quit()

    def can_send(self, email: str) -> str | None:
        """Reason this address must be skipped, or None."""
        if self.db.suppressed(email):
            return "on opt-out list"
        if self.db.already_contacted(email, domain_of(email), self.cfg.email.get("one_email_per_company", True)):
            return "company already contacted"
        if self.live and self.db.sent_today() >= int(self.cfg.email.get("daily_limit", 15)):
            return "daily limit reached"
        return None

    def send(self, msg: EmailMessage, opp_id: str) -> Path | None:
        to = msg["To"]
        if not self.live:
            self.cfg.outbox.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w.@-]", "_", to)
            path = self.cfg.outbox / f"{opp_id}_{safe}.eml"
            path.write_bytes(bytes(msg))
            return path
        wait = float(self.cfg.email.get("seconds_between", 90)) - (time.monotonic() - self.last)
        if self.last and wait > 0:
            time.sleep(wait)
        self.smtp.send_message(msg)
        self.last = time.monotonic()
        self.db.log_sent(to, domain_of(to), opp_id)
        return None
