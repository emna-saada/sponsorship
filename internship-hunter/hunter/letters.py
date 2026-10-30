"""Cover letters: a solid template per resume track, optionally tailored per posting by Claude."""
import sys
from datetime import date
from pathlib import Path

from .db import Opportunity

TEMPLATES = {
    "en": {
        "subject": "Final-year internship application: {title} ({name})",
        "spontaneous_subject": "{kind_cap} internship application, January 2027: {focus} ({name})",
        "body": """Dear {greeting},

I am {name}, a final-year student at {school} ({degree}, graduating {graduation}). I am looking \
for a {duration} end-of-studies internship starting {start}. {hook}

{pitch}

{insight}{fit}

I have attached my resume and cover letter. I would be glad to discuss how I could contribute to \
{company}.

Kind regards,
{name}
{email} · {phone}
{linkedin}""",
    },
    "fr": {
        "subject": "Candidature stage de fin d'études : {title} ({name})",
        "spontaneous_subject": "Candidature spontanée, stage de fin d'études janvier 2027 : {focus} ({name})",
        "body": """Madame, Monsieur,

Je suis {name}, étudiant(e) en dernière année à {school} ({degree}, diplôme en {graduation}). \
Je recherche un stage de fin d'études (PFE) de {duration} à partir de {start}. {hook}

{pitch}

{insight}{fit}

Vous trouverez ci-joint mon CV et ma lettre de motivation. Je serais ravi(e) d'échanger avec vous \
sur la manière dont je pourrais contribuer aux projets de {company}.

Cordialement,
{name}
{email} · {phone}
{linkedin}""",
    },
}

# (posting, spontaneous) x (professional, research)
HOOK = {
    "en": {
        ("posting", "professional"): "The {title} position caught my attention because it matches the {focus} work I want to build my career on.",
        ("posting", "research"): "The {title} position caught my attention because it matches the {focus} research I want to pursue.",
        ("spontaneous", "professional"): "I am applying spontaneously because {company}'s work in {focus} is exactly where I want to start my career.",
        ("spontaneous", "research"): "I am applying spontaneously for a research internship because your group's work in {focus} is exactly the research I want to contribute to.",
    },
    "fr": {
        ("posting", "professional"): "L'offre « {title} » correspond précisément au domaine dans lequel je souhaite évoluer ({focus}).",
        ("posting", "research"): "L'offre « {title} » correspond précisément aux travaux de recherche que je souhaite mener ({focus}).",
        ("spontaneous", "professional"): "Je vous adresse une candidature spontanée car les projets de {company} en {focus} correspondent exactement à mon projet professionnel.",
        ("spontaneous", "research"): "Je vous adresse une candidature spontanée pour un stage de recherche, car les travaux de votre équipe en {focus} correspondent exactement à ce que je souhaite approfondir.",
    },
}

FIT = {
    "en": "In particular, my experience with {skills} matches what your team is working on.",
    "fr": "En particulier, mon expérience en {skills} correspond aux besoins de votre équipe.",
}
INSIGHT = {
    "en": "I was especially interested to read about {insight}. ",
    "fr": "J'ai particulièrement été intéressé(e) par {insight}. ",
}

PRETTY = {"pytorch": "PyTorch", "tensorflow": "TensorFlow", "postgis": "PostGIS", "postgresql": "PostgreSQL",
          "geopandas": "GeoPandas", "arcgis": "ArcGIS", "arcgis pro": "ArcGIS Pro", "arcpy": "ArcPy",
          "javascript": "JavaScript", "typescript": "TypeScript", "openlayers": "OpenLayers", "geoserver": "GeoServer",
          "geojson": "GeoJSON", "openstreetmap": "OpenStreetMap", "webgis": "WebGIS", "maplibre": "MapLibre",
          "google earth engine": "Google Earth Engine", "earth engine": "Earth Engine", "python": "Python",
          "sentinel-2": "Sentinel-2", "sentinel": "Sentinel", "landsat": "Landsat", "u-net": "U-Net", "unet": "U-Net",
          "xgboost": "XGBoost", "lightgbm": "LightGBM", "keras": "Keras", "power bi": "Power BI",
          "elasticsearch": "Elasticsearch", "kibana": "Kibana", "streamlit": "Streamlit", "django": "Django",
          "docker": "Docker", "lidar": "LiDAR", "rasterio": "rasterio", "shapely": "Shapely", "pyproj": "pyproj",
          "cityjson": "CityJSON", "citygml": "CityGML", "3d tiles": "3D Tiles", "cesiumjs": "CesiumJS",
          "cesium": "Cesium", "gltf": "glTF", "laspy": "laspy", "numba": "Numba", "scipy": "SciPy",
          "numpy": "NumPy", "statsmodels": "statsmodels", "scikit-learn": "scikit-learn", "echarts": "ECharts",
          "random forest": "Random Forest", "c++": "C++", "java": "Java", "pytest": "pytest", "pandas": "pandas"}


def pretty(skill: str) -> str:
    return PRETTY.get(skill) or (skill.upper() if len(skill) <= 4 else skill)


def join(items: list[str], lang: str) -> str:
    word = " and " if lang == "en" else " et "
    return ", ".join(items[:-1]) + word + items[-1] if len(items) > 1 else "".join(items)


def _fields(profile: dict, opp: Opportunity, skills: list[str], lang: str, track=None) -> dict:
    spontaneous = opp.source in ("manual", "prospect") and not opp.url
    kind = opp.kind or "professional"
    focus = (track.focus if track and track.focus else profile.get("focus", "geospatial data"))
    title = "final-year internship" if spontaneous else opp.title
    shown = join([pretty(k) for k in skills[:5]], lang) or ("GIS, remote sensing and Python" if lang == "en" else "SIG, télédétection et Python")
    pitch = (track.pitch if track and track.pitch else profile.get("pitch", "")).strip()
    return {
        "name": profile.get("name", ""), "email": profile.get("email", ""), "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""), "school": profile.get("school", ""),
        "degree": profile.get("degree", ""), "graduation": profile.get("graduation", ""),
        "duration": profile.get("internship_duration", "6-month"), "start": profile.get("internship_start", "soon"),
        "pitch": pitch, "company": opp.company, "title": title, "focus": focus,
        "kind_cap": "Research" if kind == "research" else "Final-year",
        "greeting": f"{opp.company} research team" if kind == "research" else f"{opp.company} hiring team",
        "fit": FIT[lang].format(skills=shown),
        "insight": INSIGHT[lang].format(insight=opp.insight.rstrip(".")) if opp.insight else "",
        "hook": HOOK[lang][("spontaneous" if spontaneous else "posting", kind)].format(title=title, company=opp.company, focus=focus),
        "spontaneous": spontaneous,
    }


def template_letter(profile: dict, opp: Opportunity, skills: list[str], track=None) -> tuple[str, str]:
    lang = profile.get("letter_language", "en")
    lang = lang if lang in TEMPLATES else "en"
    t = TEMPLATES[lang]
    f = _fields(profile, opp, skills, lang, track)
    subject = (t["spontaneous_subject"] if f["spontaneous"] else t["subject"]).format(**f)
    return subject, t["body"].format(**f)


SYSTEM = """You write concise, honest cover-letter emails for a final-year student applying \
for an end-of-studies internship. Use only facts present in the resume and the company notes; \
never invent experience, grades, projects, or facts about the company. Tie two or three \
concrete resume items to the posting or to the company's work. At most 230 words. Plain text, \
no markdown, no placeholders. Start with the greeting and end with the sign-off and the \
candidate's contact lines exactly as in the draft."""


def ai_letter(cfg, opp: Opportunity, resume_text: str, draft: str) -> str | None:
    if not (cfg.ai.get("enabled", True) and cfg.secret("ANTHROPIC_API_KEY")):
        return None
    try:
        import anthropic
    except ImportError:
        print("  (pip install anthropic to enable tailored letters)", file=sys.stderr)
        return None
    lang = "French" if cfg.profile.get("letter_language") == "fr" else "English"
    notes = f"<company_notes>\n{opp.insight}\n{opp.note}\n</company_notes>\n\n" if (opp.insight or opp.note) else ""
    prompt = (f"<resume>\n{resume_text[:12000]}\n</resume>\n\n"
              f"<posting company=\"{opp.company}\" title=\"{opp.title}\" location=\"{opp.location}\" kind=\"{opp.kind}\">\n"
              f"{opp.description[:6000]}\n</posting>\n\n{notes}<template_draft>\n{draft}\n</template_draft>\n\n"
              f"Rewrite the draft in {lang} so it is specific to this posting and organization. Return only the letter.")
    try:
        client = anthropic.Anthropic()
        msg = client.beta.messages.create(
            model=cfg.ai.get("model", "claude-opus-5-5"),
            max_tokens=4000,
            system=SYSTEM,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        print(f"  AI letter failed, using template: {e}", file=sys.stderr)
        return None
    if msg.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    return text or None


def to_pdf(text: str, path: Path, profile: dict) -> Path:
    from fpdf import FPDF

    def latin(s: str) -> str:  # core PDF fonts are Latin-1 (covers French/German/Spanish accents)
        return (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
                 .replace("–", "-").replace("—", "-").replace("·", "-").replace("…", "...")
                 .encode("latin-1", "replace").decode("latin-1"))

    pdf = FPDF(format="A4")
    pdf.set_margins(22, 22, 22)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, latin(profile.get("name", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    contact = " | ".join(x for x in (profile.get("email"), profile.get("phone"), profile.get("linkedin")) if x)
    pdf.cell(0, 6, latin(contact), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, date.today().strftime("%d %B %Y"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, latin(text))
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path
