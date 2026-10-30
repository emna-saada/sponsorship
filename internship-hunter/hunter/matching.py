"""Scores how well a posting fits a final-year internship in one of the resume tracks (0-100)."""
import re

from . import geo
from .db import Opportunity
from .tracks import Track, fit, has

# Kept for older imports; tracks.has is the matcher.
_has = has

# Skills looked for in both a resume and a posting.
SKILLS = [
    "python", "sql", "postgis", "postgresql", "gdal", "qgis", "arcgis", "arcgis pro", "arcpy",
    "geopandas", "shapely", "rasterio", "pyproj", "xarray", "google earth engine", "earth engine",
    "sentinel", "sentinel-2", "landsat", "sar", "lidar", "point cloud", "point clouds", "laspy", "pdal",
    "photogrammetry", "dsm", "dtm", "cityjson", "citygml", "3d tiles", "cesiumjs", "cesium", "gltf",
    "digital twin", "pytorch", "tensorflow", "keras", "deep learning", "machine learning",
    "computer vision", "segmentation", "object detection", "image classification", "image processing",
    "remote sensing", "change detection", "ndvi", "u-net", "unet", "random forest", "lightgbm",
    "xgboost", "scikit-learn", "shap", "federated learning", "rag", "embeddings", "llm",
    "gis", "webgis", "leaflet", "openlayers", "maplibre", "mapbox", "geoserver", "geojson",
    "osm", "openstreetmap", "cartography", "geostatistics", "kriging", "spatial statistics",
    "gnss", "geodesy", "map projections", "time series", "statistics", "pandas", "numpy", "scipy",
    "statsmodels", "numba", "pytest", "git", "docker", "spark", "stac", "airflow", "dbt",
    "javascript", "typescript", "r", "c++", "java", "django", "streamlit", "echarts",
    "elasticsearch", "kibana", "power bi", "aws", "gcp", "azure", "fme", "envi",
]
# skills too ambiguous to look for in a posting by themselves
_POSTING_SKIP = {"r", "git", "rag", "shap", "dsm", "dtm"}

RESEARCH = re.compile(r"\b(research|laborator(y|ies)|laboratoire|labo|lab|institut[e]?|universit[yé]|"
                      r"thesis|thèse|master'?s? project|scientific|scientifique|CNRS|INRAE|IRD|EPFL|ETH)\b", re.I)
START_OK = re.compile(r"\b(janvier|january|jan\.?|février|fevrier|february|feb\.?)\s*(20)?27\b|\b(early|début)\s*2027\b|\b2027\b", re.I)
DURATION_OK = re.compile(r"\b[4-6]\s*(-|to|à|a)?\s*[4-6]?\s*(months?|mois|monate)\b|\b(6|six)[- ]month", re.I)
WRONG_TIME = re.compile(r"\bsummer (intern|internship|placement)|\bstage d'été\b|\b(2|3|two|three|10|11|12)[- ]?(months?|mois)\b", re.I)

PAID = re.compile(r"\b(paid (internship|placement)|stipend|salary|salaire|gratification|rémunér[ée]+|"
                  r"indemnit[ée]|allowance|compensation|remuneration|vergütung|fully funded|funded (internship|position|placement)|bourse|"
                  r"per month|par mois|/\s?month|/\s?mois|monthly)\b|[£€$¥]\s?\d|\d\s?(€|chf|eur|gbp|jpy|mad|dhs?|円)\b|"
                  r"\bchf\s?\d|\b\d+\s?万円|時給|月給", re.I)
UNPAID = re.compile(r"\b(unpaid|non[- ]?rémunér[ée]+|non[- ]?paid|volunteer(ing)?|bénévol\w*|"
                    r"no (salary|stipend|compensation)|without (pay|salary|compensation)|for (academic )?credit only)\b|無給", re.I)


def pay_status(opp: Opportunity) -> str:
    body = f"{opp.title}\n{opp.description}"
    if UNPAID.search(body):
        return "unpaid"
    if PAID.search(body):
        return "paid"
    if opp.country == "france":
        return "paid (legal gratification)"  # French law requires pay for internships over 2 months
    return "unknown"


def resume_skills(resume_text: str) -> set[str]:
    return {s for s in SKILLS if has(resume_text, s)}


def posting_skills(opp: Opportunity, skills: set[str]) -> list[str]:
    body = f"{opp.title} {opp.description}"
    return [s for s in sorted(skills) if s not in _POSTING_SKIP and has(body, s)]


def kind(opp: Opportunity) -> str:
    return "research" if RESEARCH.search(f"{opp.title} {opp.company} {opp.description[:4000]}") else "professional"


def in_scope(opp: Opportunity, search: dict) -> bool:
    targets = search.get("target_countries") or []
    if not targets:
        return True
    if opp.country in targets:
        return True
    if opp.country == "remote":
        return bool(search.get("allow_remote", True))
    # unknown location: keep leads you added yourself, drop anonymous board postings
    return opp.country == "" and opp.source in ("manual", "prospect")


def score(opp: Opportunity, search: dict, tracks: list[Track], skills_by_track: dict[str, set[str]]) -> tuple[int, list[str], str]:
    """Returns (score, matched terms, best track name). Score 0 means out of scope."""
    title, body = opp.title, f"{opp.title}\n{opp.description}"
    excluded = [k for k in search.get("exclude_keywords", []) if has(title, k)]
    if excluded:
        return 0, [f"-{k}" for k in excluded], ""
    if not in_scope(opp, search):
        return 0, [f"-country:{opp.country or 'unknown'}"], ""

    best, best_fit, domain = None, -1, []
    for t in tracks:
        f, hits = fit(opp, t)
        if f > best_fit:
            best, best_fit, domain = t, f, hits
    extra = [k for k in search.get("domain_keywords", []) if has(body, k) and k not in domain]
    domain += extra
    if not domain:
        return 0, [], ""
    intern = [k for k in search.get("internship_keywords", []) if has(body, k)]
    pay = pay_status(opp)
    if pay == "unpaid" and search.get("require_paid", True):
        return 0, ["-unpaid"], ""

    s = 0
    s += 28 if any(has(title, k) for k in domain) else 14            # specialty in the title
    s += min(len(domain), 5) * 3                                       # breadth of fit
    if intern:
        s += 28 if any(has(title, k) for k in intern) else 16         # it's an internship
    elif opp.source in ("manual", "prospect"):
        s += 18                                                        # spontaneous application
    overlap = posting_skills(opp, skills_by_track.get(best.name, set()))
    s += min(len(overlap), 6) * 3                                      # resume-skill overlap
    if START_OK.search(body):
        s += 8                                                         # starts Jan/Feb 2027
    if DURATION_OK.search(body):
        s += 5                                                         # 4-6 months
    if WRONG_TIME.search(body) and not DURATION_OK.search(body):
        s -= 20                                                        # summer / short internship
    if pay.startswith("paid"):
        s += 8                                                         # paid or funded
    return max(0, min(s, 100)), domain + intern + overlap, best.name
