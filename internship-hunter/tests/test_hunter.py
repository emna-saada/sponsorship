import email
from pathlib import Path

import pytest

from hunter import cli, config, contacts, letters, matching, sources
from hunter.db import DB, Opportunity

ROOT = Path(__file__).resolve().parent.parent
import tomllib
SEARCH = tomllib.loads((ROOT / "config.example.toml").read_text())["search"]


def opp(title, desc="", **kw):
    return Opportunity(title=title, company=kw.pop("company", "GeoCo"), description=desc, **kw)


# --- matching --------------------------------------------------------------

def test_gis_internship_scores_high():
    s, matched = matching.score(opp("GIS Intern", "Remote sensing with Python and PostGIS"), SEARCH, {"python", "postgis"})
    assert s >= 70 and "GIS" in matched


def test_french_pfe_matches():
    s, _ = matching.score(opp("Stage PFE - Télédétection et SIG", "stage de fin d'études"), SEARCH, set())
    assert s >= 60


def test_senior_role_excluded():
    assert matching.score(opp("Senior GIS Engineer", "internship mentoring"), SEARCH, set())[0] == 0


def test_non_geo_internship_excluded():
    assert matching.score(opp("Marketing Intern", "social media design"), SEARCH, set())[0] == 0


def test_full_time_geo_job_scores_below_threshold():
    s, _ = matching.score(opp("Account Manager", "We sell GIS software"), SEARCH, set())
    assert s < SEARCH["min_score"]


def test_lowercase_sig_word_not_an_acronym():
    assert not matching._has("the sig figure", "SIG")
    assert matching._has("Analyste SIG", "SIG")


# --- contacts --------------------------------------------------------------

def test_extract_prefers_recruiting_and_drops_noreply():
    text = "Write to info@geo.io or careers@geo.io. noreply@geo.io. Also jobs [at] geo.io"
    found = contacts.extract(text)
    assert found[0] in ("careers@geo.io", "jobs@geo.io")
    assert "noreply@geo.io" not in found and "info@geo.io" in found


def test_short_prefix_does_not_match_inside_names():
    assert contacts.rank("christophe@geo.io") == 20
    assert contacts.rank("hr@geo.io") > 40


def test_verify(monkeypatch):
    monkeypatch.setattr(contacts, "mx_hosts", lambda d: ("mx.geo.io",) if d == "geo.io" else ())
    assert contacts.verify("careers@geo.io") == "valid"
    assert contacts.verify("careers@nomail.zz") == "no-mail-server"
    assert contacts.verify("bad@@geo.io") == "bad-syntax"
    assert contacts.verify("x@mailinator.com") == "disposable"


# --- sources ---------------------------------------------------------------

def test_greenhouse_parsing(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda url, **p: {"jobs": [{
        "title": "GeoAI Intern", "absolute_url": "https://x/1", "location": {"name": "Berlin"},
        "content": "&lt;p&gt;Deep learning on satellite imagery&lt;/p&gt;", "updated_at": "2026-10-01T00:00"}]})
    [o] = sources._board({"company": "Planet", "ats": "greenhouse", "ats_token": "planetlabs", "website": ""})
    assert o.title == "GeoAI Intern" and "satellite imagery" in o.description and "<p>" not in o.description


def test_fetch_all_survives_a_dead_source(monkeypatch, tmp_path):
    def boom(cfg):
        raise sources.requests.ConnectionError("blocked")
    monkeypatch.setitem(sources.SOURCES, "remotive", boom)
    monkeypatch.setitem(sources.SOURCES, "jobicy", lambda cfg: [opp("GIS intern")])
    cfg = config.Config(profile={}, search={"sources": ["remotive", "jobicy"]}, email={}, ai={}, base_dir=tmp_path)
    assert len(sources.fetch_all(cfg)) == 1


# --- letters ---------------------------------------------------------------

def test_spontaneous_letter_wording():
    o = Opportunity(title="Final-year internship (spontaneous application)", company="Oslandia", source="manual")
    subject, body = letters.template_letter({"name": "Ada", "pitch": "Hi."}, o, ["qgis"])
    assert subject.startswith("Spontaneous") and "spontaneously" in body and "Oslandia" in body


# --- end to end ------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    cfg_text = (ROOT / "config.example.toml").read_text().replace('resume_pdf = "data/resume.pdf"', 'resume_pdf = "resume.pdf"')
    (tmp_path / "config.toml").write_text(cfg_text)
    letters.to_pdf("Python PostGIS QGIS remote sensing", tmp_path / "resume.pdf", {"name": "Ada"})
    (tmp_path / "leads.csv").write_text(
        "title,company,location,url,description,company_website,contact_email\n"
        "GIS Intern,GeoOne,Paris,https://g1/jobs/1,GIS internship with QGIS,,careers@geoone.io\n"
        "Remote Sensing Intern,GeoOne,Paris,https://g1/jobs/2,remote sensing internship,,jobs@geoone.io\n"
        "Data Intern,NoGeo,Rome,https://n/1,marketing data internship,,hr@nogeo.io\n"
    )
    monkeypatch.setattr(contacts, "mx_hosts", lambda d: ("mx." + d,))
    return tmp_path


def run(ws, *args):
    cli.main(["--config", str(ws / "config.toml"), *args])


def test_pipeline_dry_run(workspace):
    run(workspace, "import", str(workspace / "leads.csv"))
    db = DB(workspace / "hunter.db")
    stored = db.list()
    assert {o.company for o in stored} == {"GeoOne"}  # the non-geo internship was filtered out

    run(workspace, "enrich")
    run(workspace, "approve", "--min-score", "0")
    run(workspace, "send")  # dry run

    emls = list((workspace / "outbox").glob("*.eml"))
    assert len(emls) == 2  # dry run drafts both; per-company dedupe applies to real sends
    msg = email.message_from_bytes(emls[0].read_bytes())
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert "resume.pdf" in names and any(n.startswith("Cover_Letter_") for n in names)
    assert msg["List-Unsubscribe"]
    assert not db.conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]

    run(workspace, "report")
    assert "GeoOne" in (workspace / "output" / "opportunities.html").read_text()


def test_live_send_contacts_each_company_once(workspace, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def login(self, *a): pass
        def send_message(self, m): sent.append(m["To"])
        def quit(self): pass

    import hunter.mailer as mailer
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    run(workspace, "import", str(workspace / "leads.csv"))
    run(workspace, "enrich")
    run(workspace, "approve", "--min-score", "0")
    db = DB(workspace / "hunter.db")
    db.conn.execute("UPDATE opportunities SET contact_email='careers@geoone.io'")  # same company, twice
    db.conn.commit()
    cfg_path = workspace / "config.toml"
    cfg_path.write_text(cfg_path.read_text().replace("seconds_between = 90", "seconds_between = 0"))
    run(workspace, "send", "--live")
    assert sent == ["careers@geoone.io"]

    run(workspace, "optout", "jobs@other.io")
    assert db.suppressed("jobs@other.io")
