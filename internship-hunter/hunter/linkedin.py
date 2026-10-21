"""LinkedIn helpers. LinkedIn's terms forbid bots that message or connect for you, and
accounts that do it get restricted, so this module never touches LinkedIn: it builds
ready-to-click search links and short notes you paste yourself (about 2 minutes a day)."""
from urllib.parse import quote_plus

# Locations covering the main geospatial job markets; "Worldwide" also finds remote roles.
LOCATIONS = ["Worldwide", "European Union", "France", "Germany", "Netherlands", "Switzerland",
             "United Kingdom", "Canada", "United States", "United Arab Emirates", "Saudi Arabia",
             "Singapore", "Australia", "Tunisia", "Morocco"]
JOB_QUERIES = ["GIS intern", "geospatial internship", "remote sensing internship", "GeoAI",
               "stage SIG", "stage PFE géomatique", "geoinformatics internship", "earth observation intern"]


def job_search_url(query: str, location: str) -> str:
    # f_E=1 = "Internship" experience level; sortBy=DD = most recent first
    return (f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(query)}"
            f"&location={quote_plus(location)}&f_E=1&sortBy=DD")


def people_search_url(company: str) -> str:
    q = f'{company} (recruiter OR "talent acquisition" OR "GIS" OR "geospatial")'
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(q)}"


def connection_note(profile: dict, company: str, title: str = "") -> str:
    """LinkedIn caps connection notes at 300 characters."""
    first = (profile.get("name") or "").split(" ")[0]
    role = f" the {title} role" if title else " final-year internships"
    note = (f"Hello, I'm {first}, a final-year geoinformatics student (GIS, remote sensing, GeoAI). "
            f"I'm very interested in{role} at {company} and just sent my application. "
            f"I'd be glad to connect!")
    return note if len(note) <= 300 else note[:297] + "..."


def plan(profile: dict, opportunities) -> dict:
    return {
        "job_searches": [(q, loc, job_search_url(q, loc)) for q in JOB_QUERIES for loc in LOCATIONS],
        "people": [(o.company, o.title, people_search_url(o.company), connection_note(profile, o.company, o.title))
                   for o in opportunities],
    }
