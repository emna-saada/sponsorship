"""Scores how well a posting fits a final-year geoinformatics internship (0-100)."""
import re

from .db import Opportunity

# Skills looked for in both the resume and the posting.
SKILLS = [
    "python", "sql", "postgis", "postgresql", "gdal", "qgis", "arcgis", "arcgis pro", "arcpy",
    "geopandas", "shapely", "rasterio", "xarray", "google earth engine", "earth engine", "sentinel",
    "landsat", "sar", "lidar", "photogrammetry", "pytorch", "tensorflow", "deep learning",
    "machine learning", "computer vision", "segmentation", "object detection", "remote sensing",
    "gis", "webgis", "leaflet", "openlayers", "mapbox", "geoserver", "docker", "spark",
    "stac", "geojson", "osm", "openstreetmap", "cartography", "geostatistics", "kriging",
    "javascript", "fme", "envi", "erdas", "dbt", "airflow", "aws", "gcp", "azure",
]


def _has(text: str, term: str) -> bool:
    # word-boundary match; short all-caps acronyms (GIS, SIG, PFE) are case-sensitive
    # so that the French word "sig" or a lowercase "pfe" in a URL slug do not count
    flags = 0 if (term.isupper() and len(term) <= 4) else re.I
    return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, flags) is not None


def resume_skills(resume_text: str) -> set[str]:
    return {s for s in SKILLS if _has(resume_text, s)}


def score(opp: Opportunity, search: dict, skills: set[str]) -> tuple[int, list[str]]:
    title, body = opp.title, f"{opp.title}\n{opp.description}"
    domain = [k for k in search.get("domain_keywords", []) if _has(body, k)]
    intern = [k for k in search.get("internship_keywords", []) if _has(body, k)]
    excluded = [k for k in search.get("exclude_keywords", []) if _has(title, k)]
    if not domain or excluded:
        return 0, domain + [f"-{k}" for k in excluded]

    s = 0
    s += 30 if any(_has(title, k) for k in domain) else 15          # domain in the title
    s += min(len(domain), 5) * 3                                       # breadth of domain fit
    if intern:
        s += 30 if any(_has(title, k) for k in intern) else 18        # it's an internship
    elif opp.source == "manual":
        s += 20                                                        # spontaneous application
    overlap = [k for k in skills if _has(body, k)]
    s += min(len(overlap), 8) * 3                                      # resume-skill overlap
    if re.search(r"\bjunior\b|\bgraduate\b|\bentry", body, re.I):
        s += 4
    return min(s, 100), domain + intern + overlap
