import hashlib
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    url TEXT,
    description TEXT,
    source TEXT,
    company_website TEXT,
    posted TEXT,
    score INTEGER DEFAULT 0,
    matched TEXT,
    contact_email TEXT,
    email_status TEXT,
    status TEXT DEFAULT 'new',      -- new | approved | rejected | sent | failed
    note TEXT,
    created TEXT
);
CREATE TABLE IF NOT EXISTS sent_log (
    email TEXT,
    domain TEXT,
    opportunity_id TEXT,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS suppression (
    email TEXT PRIMARY KEY,
    reason TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Opportunity:
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""
    source: str = ""
    company_website: str = ""
    posted: str = ""
    score: int = 0
    matched: str = ""
    contact_email: str = ""
    email_status: str = ""
    status: str = "new"
    note: str = ""
    created: str = ""
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            key = (self.url or f"{self.company}|{self.title}|{self.location}").lower().strip()
            self.id = hashlib.sha1(key.encode()).hexdigest()[:16]


class DB:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert(self, opp: Opportunity) -> bool:
        """Insert a new opportunity; returns False if it was already known."""
        if self.conn.execute("SELECT 1 FROM opportunities WHERE id=?", (opp.id,)).fetchone():
            return False
        opp.created = opp.created or now()
        row = asdict(opp)
        cols = ",".join(row)
        self.conn.execute(
            f"INSERT INTO opportunities ({cols}) VALUES ({','.join('?' * len(row))})",
            list(row.values()),
        )
        self.conn.commit()
        return True

    def update(self, opp_id: str, **fields):
        sets = ",".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE opportunities SET {sets} WHERE id=?", [*fields.values(), opp_id])
        self.conn.commit()

    def get(self, opp_id: str) -> Opportunity | None:
        r = self.conn.execute("SELECT * FROM opportunities WHERE id=?", (opp_id,)).fetchone()
        return Opportunity(**dict(r)) if r else None

    def list(self, status: str | None = None, min_score: int = 0) -> list[Opportunity]:
        q, args = "SELECT * FROM opportunities WHERE score>=?", [min_score]
        if status:
            q += " AND status=?"
            args.append(status)
        q += " ORDER BY score DESC, created DESC"
        return [Opportunity(**dict(r)) for r in self.conn.execute(q, args)]

    # --- sending history -------------------------------------------------
    def already_contacted(self, email: str, domain: str, per_company: bool) -> bool:
        if per_company:
            q = "SELECT 1 FROM sent_log WHERE email=? OR domain=?"
            return bool(self.conn.execute(q, (email.lower(), domain.lower())).fetchone())
        return bool(self.conn.execute("SELECT 1 FROM sent_log WHERE email=?", (email.lower(),)).fetchone())

    def sent_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return self.conn.execute("SELECT COUNT(*) FROM sent_log WHERE sent_at LIKE ?", (today + "%",)).fetchone()[0]

    def log_sent(self, email: str, domain: str, opp_id: str):
        self.conn.execute("INSERT INTO sent_log VALUES (?,?,?,?)", (email.lower(), domain.lower(), opp_id, now()))
        self.conn.commit()

    def suppressed(self, email: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM suppression WHERE email=?", (email.lower(),)).fetchone())

    def suppress(self, email: str, reason: str = "opt-out"):
        self.conn.execute("INSERT OR REPLACE INTO suppression VALUES (?,?)", (email.lower(), reason))
        self.conn.commit()

    def stats(self) -> dict:
        rows = self.conn.execute("SELECT status, COUNT(*) FROM opportunities GROUP BY status").fetchall()
        return {r[0]: r[1] for r in rows}
