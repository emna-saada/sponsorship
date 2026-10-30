"""Job sources. Each fetcher returns a list of Opportunity objects and never raises:
a source that is down or blocked is reported and skipped."""
import csv
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from .db import Opportunity

UA = "internship-hunter/1.0 (personal job search tool)"
TIMEOUT = 25

# Short queries sent to sources that support search; the matcher does the real filtering.
QUERIES = ["gis intern", "geospatial intern", "remote sensing intern", "geoinformatics", "gis", "geospatial"]


def queries(cfg) -> list[str]:
    """Search phrases: each resume track's queries, or the defaults."""
    out = [q for t in cfg.raw.get("tracks", []) for q in t.get("queries", [])]
    return list(dict.fromkeys(out)) or QUERIES


def strip_html(text: str) -> str:
    text = re.sub(r"<(br|/p|/li|/div)[^>]*>", "\n", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html.unescape(text)).strip()


def _get(url: str, **params):
    r = requests.get(url, params=params or None, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _epoch(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts) / (1000 if int(ts) > 10**11 else 1), timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return str(ts or "")[:10]


def arbeitnow(cfg) -> list[Opportunity]:
    out = []
    for page in range(1, 6):
        data = _get("https://www.arbeitnow.com/api/job-board-api", page=page)
        for j in data.get("data", []):
            out.append(Opportunity(
                title=j["title"], company=j["company_name"], location=j.get("location", ""),
                url=j["url"], description=strip_html(j.get("description", "")) + " " + " ".join(j.get("tags", []) + j.get("job_types", [])),
                source="arbeitnow", posted=_epoch(j.get("created_at")),
            ))
        if not data.get("links", {}).get("next"):
            break
    return out


def remotive(cfg) -> list[Opportunity]:
    out = []
    for q in queries(cfg):
        for j in _get("https://remotive.com/api/remote-jobs", search=q).get("jobs", []):
            out.append(Opportunity(
                title=j["title"], company=j["company_name"],
                location="Remote · " + (j.get("candidate_required_location") or "Worldwide"),
                url=j["url"], description=strip_html(j.get("description", "")) + " " + (j.get("job_type") or ""),
                source="remotive", posted=str(j.get("publication_date", ""))[:10],
            ))
    return out


def remoteok(cfg) -> list[Opportunity]:
    out = []
    for tag in ("gis", "geospatial", "internship"):
        for j in _get("https://remoteok.com/api", tag=tag):
            if not isinstance(j, dict) or "position" not in j:
                continue  # first element is the API's legal notice
            out.append(Opportunity(
                title=j["position"], company=j.get("company", ""), location="Remote · " + (j.get("location") or "Worldwide"),
                url=j.get("url", ""), description=strip_html(j.get("description", "")) + " " + " ".join(j.get("tags", [])),
                source="remoteok", posted=str(j.get("date", ""))[:10],
            ))
    return out


def jobicy(cfg) -> list[Opportunity]:
    out = []
    for tag in ("gis", "geospatial", "remote-sensing", "data"):
        for j in _get("https://jobicy.com/api/v2/remote-jobs", count=50, tag=tag).get("jobs", []):
            out.append(Opportunity(
                title=j.get("jobTitle", ""), company=j.get("companyName", ""), location="Remote · " + (j.get("jobGeo") or "Worldwide"),
                url=j.get("url", ""), description=strip_html(j.get("jobDescription", "")) + " " + " ".join(j.get("jobType") or []),
                source="jobicy", posted=str(j.get("pubDate", ""))[:10],
            ))
    return out


def adzuna(cfg) -> list[Opportunity]:
    app_id, app_key = cfg.secret("ADZUNA_APP_ID"), cfg.secret("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("  adzuna: skipped (set ADZUNA_APP_ID and ADZUNA_APP_KEY for 19-country coverage)")
        return []
    out = []
    for country in cfg.search.get("adzuna_countries", []):
        for what in queries(cfg):
            try:
                data = _get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                            app_id=app_id, app_key=app_key, what=what, results_per_page=50)
            except requests.RequestException as e:
                print(f"  adzuna/{country}: {e}", file=sys.stderr)
                break
            for j in data.get("results", []):
                out.append(Opportunity(
                    title=strip_html(j.get("title", "")), company=j.get("company", {}).get("display_name", ""),
                    location=f"{j.get('location', {}).get('display_name', '')} ({country.upper()})",
                    url=j.get("redirect_url", ""), description=strip_html(j.get("description", "")),
                    source=f"adzuna-{country}", posted=str(j.get("created", ""))[:10],
                ))
    return out


def reed(cfg) -> list[Opportunity]:
    """Reed.co.uk, the largest UK job board (free key: reed.co.uk/developers/jobseeker)."""
    key = cfg.secret("REED_API_KEY")
    if not key:
        print("  reed: skipped (set REED_API_KEY for UK coverage)")
        return []
    out = []
    for q in queries(cfg):
        r = requests.get("https://www.reed.co.uk/api/1.0/search", params={"keywords": q, "resultsToTake": 100},
                         auth=(key, ""), headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        for j in r.json().get("results", []):
            out.append(Opportunity(
                title=j.get("jobTitle", ""), company=j.get("employerName", ""),
                location=f"{j.get('locationName', '')}, United Kingdom", url=j.get("jobUrl", ""),
                description=strip_html(j.get("jobDescription", "")) + (
                    f" Salary {j['minimumSalary']}-{j.get('maximumSalary')} GBP" if j.get("minimumSalary") else ""),
                source="reed", posted=str(j.get("date", ""))[:10],
            ))
    return out


def francetravail(cfg) -> list[Opportunity]:
    """France Travail (ex Pôle emploi) official API (free app: francetravail.io)."""
    cid, secret = cfg.secret("FRANCETRAVAIL_CLIENT_ID"), cfg.secret("FRANCETRAVAIL_CLIENT_SECRET")
    if not (cid and secret):
        print("  francetravail: skipped (set FRANCETRAVAIL_CLIENT_ID and FRANCETRAVAIL_CLIENT_SECRET for France)")
        return []
    tok = requests.post("https://entreprise.francetravail.fr/connexion/oauth2/access_token",
                        params={"realm": "/partenaire"},
                        data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret,
                              "scope": "api_offresdemploiv2 o2dsoffre"}, timeout=TIMEOUT)
    tok.raise_for_status()
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}", "User-Agent": UA}
    out = []
    for q in ("stage SIG", "stage géomatique", "stage télédétection", "stage LiDAR", "stage data science",
              "stage fin d'études SIG"):
        r = requests.get("https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search",
                         params={"motsCles": q, "range": "0-149"}, headers=headers, timeout=TIMEOUT)
        if r.status_code == 204:  # no results
            continue
        r.raise_for_status()
        for j in r.json().get("resultats", []):
            contact = j.get("contact") or {}
            out.append(Opportunity(
                title=j.get("intitule", ""), company=(j.get("entreprise") or {}).get("nom", "") or "Entreprise (France Travail)",
                location=f"{(j.get('lieuTravail') or {}).get('libelle', '')}, France",
                url=(j.get("origineOffre") or {}).get("urlOrigine", ""),
                description=(j.get("description") or "") + " " + ((j.get("salaire") or {}).get("libelle") or ""),
                company_website=(j.get("entreprise") or {}).get("url", "") or "",
                contact_email=(contact.get("courriel") or "") if "@" in (contact.get("courriel") or "") else "",
                source="francetravail", posted=str(j.get("dateCreation", ""))[:10],
            ))
    return out


# --- company career boards (Greenhouse / Lever / Ashby public APIs) --------

def load_companies(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("company") and not r["company"].startswith("#")]


def _board(company: dict) -> list[Opportunity]:
    ats, token, name = company.get("ats", "").strip().lower(), company.get("ats_token", "").strip(), company["company"]
    site = company.get("website", "")
    if ats == "greenhouse":
        jobs = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", content="true").get("jobs", [])
        return [Opportunity(title=j["title"], company=name, location=(j.get("location") or {}).get("name", ""),
                            url=j.get("absolute_url", ""), description=strip_html(html.unescape(j.get("content", ""))),
                            source="greenhouse", company_website=site, posted=str(j.get("updated_at", ""))[:10]) for j in jobs]
    if ats == "lever":
        jobs = _get(f"https://api.lever.co/v0/postings/{token}", mode="json")
        return [Opportunity(title=j.get("text", ""), company=name, location=(j.get("categories") or {}).get("location", ""),
                            url=j.get("hostedUrl", ""),
                            description=(j.get("descriptionPlain") or "") + " " + ((j.get("categories") or {}).get("commitment") or ""),
                            source="lever", company_website=site, posted=_epoch(j.get("createdAt"))) for j in jobs]
    if ats == "ashby":
        jobs = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}").get("jobs", [])
        return [Opportunity(title=j.get("title", ""), company=name, location=j.get("location", ""),
                            url=j.get("jobUrl", ""), description=(j.get("descriptionPlain") or "") + " " + (j.get("employmentType") or ""),
                            source="ashby", company_website=site, posted=str(j.get("publishedAt", ""))[:10]) for j in jobs]
    return []


def ats(cfg) -> list[Opportunity]:
    out = []
    for c in load_companies(cfg.path("data/companies.csv")):
        if not c.get("ats"):
            continue
        try:
            out += _board(c)
        except (requests.RequestException, ValueError) as e:
            print(f"  {c['ats']}/{c['ats_token']} ({c['company']}): {e}", file=sys.stderr)
    return out


def import_csv(path: Path) -> list[Opportunity]:
    """Opportunities you collected yourself (LinkedIn, EURAXESS, school job board, a friend...).
    Columns: title,company,location,url,description,company_website,contact_email
    Optional: track (data/geoinformatics/gis/lidar), company_linkedin"""
    with open(path, newline="", encoding="utf-8") as f:
        return [Opportunity(
            title=r.get("title") or "Final-year internship (spontaneous application)",
            company=r["company"], location=r.get("location", ""), url=r.get("url", ""),
            description=r.get("description", ""), company_website=r.get("company_website", ""),
            contact_email=(r.get("contact_email") or "").strip(), source="manual",
            track=(r.get("track") or "").strip(), company_linkedin=(r.get("company_linkedin") or "").strip(),
        ) for r in csv.DictReader(f) if r.get("company")]


SOURCES = {"arbeitnow": arbeitnow, "remotive": remotive, "remoteok": remoteok, "jobicy": jobicy,
           "adzuna": adzuna, "reed": reed, "francetravail": francetravail, "ats": ats}


def fetch_all(cfg) -> list[Opportunity]:
    out = []
    for name in cfg.search.get("sources", list(SOURCES)):
        fn = SOURCES.get(name)
        if not fn:
            print(f"  unknown source '{name}'", file=sys.stderr)
            continue
        try:
            got = fn(cfg)
            print(f"  {name}: {len(got)} postings")
            out += got
        except (requests.RequestException, ValueError) as e:
            print(f"  {name}: unavailable ({e.__class__.__name__}: {str(e)[:120]})", file=sys.stderr)
    return out
