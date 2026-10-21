"""Find and verify recruiting emails.

Emails come only from public places: the job posting itself, or the company's own
website (homepage, careers, contact, about pages, honoring robots.txt). Nothing is
guessed: an address is kept only if it was published and its domain accepts mail."""
import re
import smtplib
import socket
from functools import lru_cache
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests

from .sources import UA, strip_html

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
STRICT_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9])?@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}$")

PREFERRED = ["internship", "internships", "stage", "stages", "intern", "jobs", "careers", "career",
             "recruiting", "recruitment", "recrutement", "talent", "hr", "rh", "people", "hiring",
             "apply", "candidature", "join", "work", "emploi", "bewerbung", "karriere"]
GENERIC = ["hello", "hi", "info", "contact", "office", "team", "mail", "admin"]
BLOCKED = ["noreply", "no-reply", "donotreply", "privacy", "gdpr", "dpo", "abuse", "security",
           "legal", "billing", "invoice", "support", "sales", "press", "media", "webmaster",
           "postmaster", "unsubscribe", "example", "sentry", "wixpress", "yourname", "name@", "email@"]
# Job-board / mail-provider domains: an address there is not the employer's.
FOREIGN_DOMAINS = {"example.com", "sentry.io", "wixpress.com", "linkedin.com", "indeed.com",
                   "arbeitnow.com", "remotive.com", "remoteok.com", "jobicy.com", "adzuna.com",
                   "greenhouse.io", "lever.co", "ashbyhq.com", "w3.org", "schema.org", "godaddy.com"}
DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com", "trashmail.com"}
CONTACT_PATHS = ["", "/careers", "/jobs", "/join-us", "/contact", "/contact-us", "/about", "/en/careers", "/carrieres"]


def domain_of(email_or_url: str) -> str:
    if "@" in email_or_url:
        return email_or_url.rsplit("@", 1)[1].lower()
    host = urlparse(email_or_url if "//" in email_or_url else "//" + email_or_url).hostname or ""
    return host.lower().removeprefix("www.")


def rank(email: str) -> int:
    """Higher is better; negative means do not use."""
    local = email.split("@")[0].lower()
    if any(b in email.lower() for b in BLOCKED) or domain_of(email) in FOREIGN_DOMAINS:
        return -1
    if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js)$", email, re.I):
        return -1
    for i, p in enumerate(PREFERRED):
        # short prefixes like "hr" must stand alone, or "christophe@" would count as HR
        if local == p or local.startswith((p + ".", p + "-", p + "_")) or (len(p) > 3 and p in local):
            return 100 - i
    if local in GENERIC:
        return 40
    return 20  # a named person's address published on the page


def extract(text: str) -> list[str]:
    text = text.replace("[at]", "@").replace("(at)", "@").replace(" [dot] ", ".").replace("[dot]", ".")
    seen = []
    for e in EMAIL_RE.findall(text):
        e = e.strip(".").lower()
        if e not in seen and rank(e) >= 0:
            seen.append(e)
    return sorted(seen, key=rank, reverse=True)


@lru_cache(maxsize=512)
def _robots(base: str) -> robotparser.RobotFileParser:
    rp = robotparser.RobotFileParser()
    try:
        r = requests.get(urljoin(base, "/robots.txt"), headers={"User-Agent": UA}, timeout=10)
        rp.parse(r.text.splitlines() if r.ok else [])
    except requests.RequestException:
        rp.parse([])
    return rp


def from_website(website: str) -> list[str]:
    if not website:
        return []
    base = website if website.startswith("http") else "https://" + website
    site_domain = domain_of(base)
    found: list[str] = []
    for path in CONTACT_PATHS:
        url = urljoin(base, path)
        if not _robots(base).can_fetch(UA, url):
            continue
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        except requests.RequestException:
            continue
        if not r.ok or "html" not in r.headers.get("content-type", ""):
            continue
        mailtos = re.findall(r'mailto:([^"\'?>\s]+)', r.text, re.I)
        for e in extract(" ".join(mailtos) + " " + strip_html(r.text)):
            # keep the company's own domain (or a subdomain of it)
            d = domain_of(e)
            if (d == site_domain or d.endswith("." + site_domain) or site_domain.endswith("." + d)) and e not in found:
                found.append(e)
    return sorted(found, key=rank, reverse=True)


# --- verification ---------------------------------------------------------

@lru_cache(maxsize=1024)
def mx_hosts(domain: str) -> tuple[str, ...]:
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        return tuple(str(r.exchange).rstrip(".") for r in sorted(answers, key=lambda r: r.preference))
    except ImportError:
        pass
    except Exception:
        return ()
    try:  # no dnspython: an A record is the RFC 5321 fallback for mail delivery
        socket.getaddrinfo(domain, 25)
        return (domain,)
    except OSError:
        return ()


def smtp_probe(email: str, mx: str, sender: str) -> bool | None:
    """True/False if the server answers RCPT TO clearly, None if it would not say."""
    try:
        with smtplib.SMTP(mx, 25, timeout=10) as s:
            s.helo("localhost")
            s.mail(sender)
            code, _ = s.rcpt(email)
            return True if code in (250, 251) else False if code in (550, 551, 553) else None
    except (OSError, smtplib.SMTPException):
        return None


def verify(email: str, sender: str = "", probe: bool = False) -> str:
    """Returns 'valid', 'accept-unknown', or a reason it is unusable."""
    if not STRICT_RE.match(email):
        return "bad-syntax"
    d = domain_of(email)
    if d in DISPOSABLE:
        return "disposable"
    if rank(email) < 0:
        return "role-blocked"
    hosts = mx_hosts(d)
    if not hosts:
        return "no-mail-server"
    if probe and sender:
        result = smtp_probe(email, hosts[0], sender)
        if result is False:
            return "mailbox-rejected"
        if result is None:
            return "accept-unknown"
    return "valid"


def find_contact(opp, sender: str = "", probe: bool = False) -> tuple[str, str]:
    """Best verified email for an opportunity, with its status."""
    candidates = ([opp.contact_email] if opp.contact_email else []) + extract(opp.description)
    if not candidates and opp.company_website:
        candidates = from_website(opp.company_website)
    last = "not-found"
    for e in candidates:
        status = verify(e, sender, probe)
        if status in ("valid", "accept-unknown"):
            return e, status
        last = f"{e}: {status}"
    return "", last
