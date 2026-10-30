import email
import tomllib
from pathlib import Path

import pytest

from hunter import cli, config, contacts, geo, letters, matching, sources, tracks
from hunter.db import DB, Opportunity

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = tomllib.loads((ROOT / "config.example.toml").read_text())
SEARCH = EXAMPLE["search"]
CFG = config.Config(profile=EXAMPLE["profile"], search=SEARCH, email={}, ai={}, raw=EXAMPLE, base_dir=ROOT)
TRACKS = tracks.load(CFG)
SKILLS = {"geoinformatics": {"python", "pytorch", "sentinel-2", "u-net"}, "gis": {"qgis", "geopandas"},
          "lidar": {"laspy", "cityjson", "point cloud"}, "data": {"xgboost", "scikit-learn"}}


def opp(title, desc="", location="Zurich, Switzerland", **kw):
    o = Opportunity(title=title, company=kw.pop("company", "GeoCo"), description=desc, location=location, **kw)
    o.country = geo.country(o.location, o.description)
    return o


def score(o):
    return matching.score(o, SEARCH, TRACKS, SKILLS)


# --- matching and tracks ----------------------------------------------------

def test_gis_internship_scores_high_and_picks_gis_resume():
    s, matched, track = score(opp("GIS Intern", "QGIS spatial analysis internship, 6 months from January 2027"))
    assert s >= 70 and track == "gis" and "GIS" in matched


def test_each_specialty_gets_its_resume():
    assert score(opp("LiDAR point cloud intern", "3D city models"))[2] == "lidar"
    assert score(opp("Earth observation intern", "Sentinel-2 remote sensing"))[2] == "geoinformatics"
    assert score(opp("Data Science Intern", "machine learning and statistics"))[2] == "data"


def test_french_pfe_matches():
    s, _, _ = score(opp("Stage PFE - Télédétection et SIG", "stage de fin d'études, gratification", "Toulouse"))
    assert s >= 60


def test_senior_role_excluded():
    assert score(opp("Senior GIS Engineer", "internship mentoring"))[0] == 0


def test_unrelated_internship_excluded():
    assert score(opp("Marketing Intern", "social media design"))[0] == 0


def test_country_outside_targets_excluded():
    assert score(opp("GIS Intern", "QGIS", location="Berlin, Germany"))[0] == 0
    assert score(opp("GIS Intern", "QGIS", location="Tokyo, Japan"))[0] > 0
    assert score(opp("GIS Intern", "QGIS", location="Remote · Worldwide"))[0] > 0


def test_unpaid_internship_excluded_and_paid_ranks_higher():
    base = score(opp("GIS Intern", "QGIS internship"))[0]
    assert score(opp("GIS Intern", "QGIS internship, unpaid"))[0] == 0
    assert score(opp("GIS Intern", "QGIS internship, stipend CHF 2500 per month"))[0] > base


def test_summer_internship_penalized():
    good = score(opp("GIS Intern", "6 months from January 2027"))[0]
    assert score(opp("GIS Intern", "summer internship, 3 months"))[0] < good


def test_research_kind_detected():
    assert matching.kind(opp("Remote sensing intern", "Join our research laboratory")) == "research"
    assert matching.kind(opp("GIS intern", "Our consulting team")) == "professional"


def test_countries():
    assert geo.country("Benguerir, Morocco") == "morocco"
    assert geo.country("東京都 港区") == "japan"
    assert geo.country("London (GB)") == "uk"
    assert geo.country("Lausanne") == "switzerland"
    assert geo.country("New York, USA") == ""


def test_short_acronyms_are_case_sensitive():
    assert not tracks.has("the sig figure", "SIG")
    assert tracks.has("Analyste SIG", "SIG")
    assert not tracks.has("GeoAI startup", "AI")
    assert tracks.has("インターンシップ募集", "インターン")


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


# --- sources and research ----------------------------------------------------

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


def test_research_json_and_emails_need_a_source():
    from hunter import research
    text = 'Found it.\n```json\n{"name": "X", "website": "https://x.ch", "emails": [' \
           '{"email": "jobs@x.ch", "source_url": "https://x.ch/careers"}, {"email": "guess@x.ch", "source_url": ""}]}\n```'
    info = research.parse_json(text)
    assert info["name"] == "X" and research.emails_from(info) == ["jobs@x.ch"]


# --- letters ---------------------------------------------------------------

def test_spontaneous_research_letter_uses_track_pitch():
    o = Opportunity(title="Final-year internship (spontaneous application)", company="ETH PRS",
                    source="prospect", kind="research", insight="your 3D point cloud benchmark")
    lidar = next(t for t in TRACKS if t.name == "lidar")
    subject, body = letters.template_letter({"name": "Ada"}, o, ["laspy", "cityjson"], lidar)
    assert subject.startswith("Research internship") and "LiDAR, 3D mapping and digital twins" in body
    assert lidar.pitch in body and "3D point cloud benchmark" in body and "laspy and CityJSON" in body


# --- end to end ------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text((ROOT / "config.example.toml").read_text())
    (tmp_path / "data").mkdir()
    for t in ("geoinformatics", "gis", "lidar", "data"):
        letters.to_pdf(f"{t} resume: Python QGIS laspy CityJSON Sentinel-2", tmp_path / "data" / f"resume_{t}.pdf", {"name": "Ada"})
    (tmp_path / "leads.csv").write_text(
        "title,company,location,url,description,company_website,contact_email\n"
        "GIS Intern,GeoOne,Paris,https://g1/jobs/1,GIS internship with QGIS,,careers@geoone.io\n"
        "LiDAR Intern,GeoOne,Paris,https://g1/jobs/2,point cloud internship,,jobs@geoone.io\n"
        "Data Intern,NoGeo,Rome,https://n/1,marketing data internship,,hr@nogeo.io\n"
    )
    monkeypatch.setattr(contacts, "mx_hosts", lambda d: ("mx." + d,))
    return tmp_path


def run(ws, *args):
    cli.main(["--config", str(ws / "config.toml"), *args])


def test_pipeline_dry_run_sends_the_right_resume(workspace):
    run(workspace, "import", str(workspace / "leads.csv"))
    db = DB(workspace / "hunter.db")
    assert {o.company for o in db.list()} == {"GeoOne"}  # the marketing internship is out of scope

    run(workspace, "enrich")
    run(workspace, "approve", "--min-score", "0")
    run(workspace, "send")  # dry run

    attached = {}
    for eml in (workspace / "outbox").glob("*.eml"):
        msg = email.message_from_bytes(eml.read_bytes())
        names = [p.get_filename() for p in msg.walk() if p.get_filename()]
        assert any(n.startswith("Cover_Letter_") for n in names) and msg["List-Unsubscribe"]
        attached[msg["To"]] = [n for n in names if n.startswith("resume_")][0]
    assert attached == {"careers@geoone.io": "resume_gis.pdf", "jobs@geoone.io": "resume_lidar.pdf"}
    assert not db.conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]

    run(workspace, "report")
    html = (workspace / "output" / "opportunities.html").read_text()
    assert "GeoOne" in html and "resume: lidar" in html and "Japan" in html


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
    cfg_path = workspace / "config.toml"
    cfg_path.write_text(cfg_path.read_text().replace("seconds_between = 90", "seconds_between = 0"))
    run(workspace, "send", "--live")
    assert len(sent) == 1  # two GeoOne offers, one email to the company

    run(workspace, "optout", "jobs@other.io")
    assert DB(workspace / "hunter.db").suppressed("jobs@other.io")


def test_old_database_is_upgraded(tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE opportunities (id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT, url TEXT, "
                 "description TEXT, source TEXT, company_website TEXT, posted TEXT, score INTEGER, matched TEXT, "
                 "contact_email TEXT, email_status TEXT, status TEXT, note TEXT, created TEXT)")
    conn.commit()
    conn.close()
    db = DB(tmp_path / "old.db")
    assert db.upsert(Opportunity(title="t", company="c", pay="paid", track="gis"))
