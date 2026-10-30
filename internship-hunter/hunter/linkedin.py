"""LinkedIn helpers. LinkedIn's terms forbid bots that message or connect for you, and
accounts that do it get restricted, so this module never touches LinkedIn: it builds
ready-to-click search links and short notes you paste yourself (a few minutes a day)."""
from urllib.parse import quote_plus

from . import geo

DEFAULT_QUERIES = ["GIS intern", "geospatial internship", "remote sensing internship", "GeoAI intern",
                   "LiDAR intern", "data science intern"]


def job_search_url(query: str, location: str) -> str:
    # f_E=1 = "Internship" experience level; sortBy=DD = most recent first
    return (f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(query)}"
            f"&location={quote_plus(location)}&f_E=1&sortBy=DD")


def people_search_url(company: str, research: bool = False) -> str:
    who = '(professor OR researcher OR "PhD")' if research else '(recruiter OR "talent acquisition" OR "HR")'
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(f'{company} {who}')}"


def connection_note(profile: dict, company: str, title: str = "", focus: str = "") -> str:
    """LinkedIn caps connection notes at 300 characters."""
    first = (profile.get("name") or "").split(" ")[0]
    about = f" ({focus})" if focus else " (GIS, remote sensing, GeoAI)"
    role = f" the {title} role" if title and "spontaneous" not in title else " a 4-6 month internship from January 2027"
    note = (f"Hello, I'm {first}, a final-year geomatics engineering student{about}. "
            f"I'm very interested in{role} at {company} and have sent my application by email. "
            f"I'd be glad to connect!")
    return note if len(note) <= 300 else note[:297] + "..."


def queries(cfg) -> list[str]:
    out = [q for t in cfg.raw.get("tracks", []) for q in t.get("linkedin_queries", t.get("queries", []))[:2]]
    return list(dict.fromkeys(out)) or DEFAULT_QUERIES


def locations(cfg) -> list[str]:
    return [geo.LABELS.get(c, c) for c in cfg.search.get("target_countries", [])] or ["Worldwide"]


def plan(cfg, opportunities) -> dict:
    focus = {t.get("name"): t.get("focus", "") for t in cfg.raw.get("tracks", [])}
    return {
        "job_searches": [(q, loc, job_search_url(q, loc)) for q in queries(cfg) for loc in locations(cfg)],
        "people": [(o.company, o.title, o.company_linkedin or people_search_url(o.company, o.kind == "research"),
                    connection_note(cfg.profile, o.company, o.title, focus.get(o.track, "")))
                   for o in opportunities],
    }
