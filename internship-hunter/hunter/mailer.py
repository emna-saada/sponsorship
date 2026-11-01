"""Sends applications by SMTP with the safety rails that keep your mailbox out of spam
folders: a daily cap, a pause between emails, one email per company, and an opt-out list.
Dry-run (the default) writes .eml files to outbox/ instead of sending."""
import imaplib
import re
import smtplib
import ssl
import time
from datetime import date, timedelta, timezone
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.utils import formatdate, getaddresses, make_msgid, parsedate_to_datetime
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


def _sent_folder(imap) -> str:
    """Name of the Sent folder, whatever the mailbox language ("[Gmail]/Sent Mail",
    "[Gmail]/Messages envoyés", ...), found through the IMAP \\Sent flag."""
    _, boxes = imap.list()
    for raw in boxes or []:
        line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        m = re.match(r'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$', line)
        if m and "\\sent" in m.group("flags").lower():
            return m.group("name").strip()
    return '"[Gmail]/Sent Mail"'


def sync_sent(cfg, db, days: int = 365) -> int:
    """Records every address you emailed from this mailbox in the last `days` days, so the
    tool never writes again to an organization you already contacted, even by hand or
    after hunter.db was deleted. Returns how many new addresses were recorded."""
    user = cfg.email.get("smtp_user") or cfg.profile.get("email")
    password = cfg.secret("SMTP_PASSWORD")
    if not password:
        raise SystemExit("Set SMTP_PASSWORD (your Gmail app password) first.")
    known = {r[0] for r in db.conn.execute("SELECT email FROM sent_log")}
    added = 0
    imap = imaplib.IMAP4_SSL(cfg.email.get("imap_host", "imap.gmail.com"), ssl_context=ssl.create_default_context())
    try:
        imap.login(user, password)
        imap.select(_sent_folder(imap), readonly=True)
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        _, data = imap.search(None, f"SINCE {since}")
        ids = (data[0] or b"").split()
        parser = BytesHeaderParser()
        for i in range(0, len(ids), 200):
            _, parts = imap.fetch(b",".join(ids[i:i + 200]), "(BODY.PEEK[HEADER.FIELDS (TO CC BCC DATE)])")
            for part in parts:
                if not isinstance(part, tuple):
                    continue
                headers = parser.parsebytes(part[1])
                try:
                    when = parsedate_to_datetime(headers["Date"]).astimezone(timezone.utc).isoformat(timespec="seconds")
                except (TypeError, ValueError):
                    when = None
                values = [v for k in ("To", "Cc", "Bcc") for v in headers.get_all(k, [])]
                for _, addr in getaddresses(values):
                    addr = addr.strip().lower()
                    if "@" in addr and addr not in known:
                        known.add(addr)
                        db.log_sent(addr, domain_of(addr), "gmail-sent", when, commit=False)
                        added += 1
        db.conn.commit()
    finally:
        try:
            imap.logout()
        except (OSError, imaplib.IMAP4.error):
            pass
    return added


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

    def can_send(self, email: str, company: str = "") -> str | None:
        """Reason this address must be skipped, or None."""
        if self.db.suppressed(email):
            return "on opt-out list"
        if self.db.already_contacted(email, domain_of(email), self.cfg.email.get("one_email_per_company", True), company):
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
