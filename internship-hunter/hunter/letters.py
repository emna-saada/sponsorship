"""Cover letters: a solid template, optionally tailored per posting by Claude."""
import sys
from datetime import date
from pathlib import Path

from .db import Opportunity

TEMPLATES = {
    "en": {
        "subject": "Final-year internship application: {title} ({name})",
        "spontaneous_subject": "Spontaneous application: final-year geospatial internship ({name})",
        "body": """Dear {company} hiring team,

I am {name}, a final-year student at {school} ({degree}, graduating {graduation}). I am looking \
for a {duration} end-of-studies internship starting {start}. {hook}

{pitch}

{fit}

I have attached my resume and cover letter. I would be glad to discuss how I could contribute to \
{company}, remotely or on site.

Kind regards,
{name}
{email} · {phone}
{linkedin}""",
    },
    "fr": {
        "subject": "Candidature stage de fin d'études : {title} ({name})",
        "spontaneous_subject": "Candidature spontanée : stage de fin d'études en géomatique ({name})",
        "body": """Madame, Monsieur,

Je suis {name}, étudiant(e) en dernière année à {school} ({degree}, diplôme en {graduation}). \
Je recherche un stage de fin d'études (PFE) de {duration} à partir de {start}. {hook}

{pitch}

{fit}

Vous trouverez ci-joint mon CV et ma lettre de motivation. Je serais ravi(e) d'échanger avec vous \
sur la manière dont je pourrais contribuer aux projets de {company}, à distance ou sur site.

Cordialement,
{name}
{email} · {phone}
{linkedin}""",
    },
}

HOOK = {
    "en": ("The {title} position caught my attention because it sits right at the intersection of "
           "geospatial data and the work I want to do.",
           "I am applying spontaneously because {company}'s geospatial work is exactly where I want to start my career."),
    "fr": ("L'offre « {title} » correspond précisément au domaine dans lequel je souhaite évoluer.",
           "Je vous adresse une candidature spontanée car les projets géospatiaux de {company} correspondent "
           "exactement au domaine dans lequel je souhaite évoluer."),
}

FIT = {
    "en": "In particular, my experience with {skills} matches what your team is working on.",
    "fr": "En particulier, mon expérience en {skills} correspond aux besoins de votre équipe.",
}


PRETTY = {"pytorch": "PyTorch", "tensorflow": "TensorFlow", "postgis": "PostGIS", "postgresql": "PostgreSQL",
          "geopandas": "GeoPandas", "arcgis": "ArcGIS", "arcgis pro": "ArcGIS Pro", "arcpy": "ArcPy",
          "javascript": "JavaScript", "openlayers": "OpenLayers", "geoserver": "GeoServer", "geojson": "GeoJSON",
          "openstreetmap": "OpenStreetMap", "webgis": "WebGIS", "google earth engine": "Google Earth Engine"}


def pretty(skill: str) -> str:
    return PRETTY.get(skill) or (skill.upper() if len(skill) <= 4 else skill.capitalize())


def _fields(profile: dict, opp: Opportunity, skills: list[str], lang: str) -> dict:
    spontaneous = opp.source == "manual" and not opp.url
    title = "final-year internship" if spontaneous else opp.title
    shown = ", ".join(pretty(k) for k in skills[:5]) if skills else ("GIS, remote sensing and Python" if lang == "en" else "SIG, télédétection et Python")
    return {
        "name": profile.get("name", ""), "email": profile.get("email", ""), "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""), "school": profile.get("school", ""),
        "degree": profile.get("degree", ""), "graduation": profile.get("graduation", ""),
        "duration": profile.get("internship_duration", "6-month"), "start": profile.get("internship_start", "soon"),
        "pitch": profile.get("pitch", "").strip(), "company": opp.company, "title": title,
        "fit": FIT[lang].format(skills=shown),
        "hook": HOOK[lang][spontaneous].format(title=title, company=opp.company),
    }


def template_letter(profile: dict, opp: Opportunity, skills: list[str]) -> tuple[str, str]:
    lang = profile.get("letter_language", "en")
    t = TEMPLATES.get(lang, TEMPLATES["en"])
    f = _fields(profile, opp, skills, lang if lang in FIT else "en")
    return (t["subject"] if opp.url or opp.source != "manual" else t["spontaneous_subject"]).format(**f), t["body"].format(**f)


SYSTEM = """You write concise, honest cover-letter emails for a final-year student applying \
for an end-of-studies internship. Use only facts present in the resume; never invent \
experience, grades, or projects. Tie two or three concrete resume items to the posting. \
At most 220 words. Plain text, no markdown, no placeholders. Start with the greeting and \
end with the sign-off and the candidate's contact line."""


def ai_letter(cfg, opp: Opportunity, resume_text: str, draft: str) -> str | None:
    if not (cfg.ai.get("enabled", True) and cfg.secret("ANTHROPIC_API_KEY")):
        return None
    try:
        import anthropic
    except ImportError:
        print("  (pip install anthropic to enable tailored letters)", file=sys.stderr)
        return None
    lang = "French" if cfg.profile.get("letter_language") == "fr" else "English"
    prompt = (f"<resume>\n{resume_text[:12000]}\n</resume>\n\n"
              f"<posting company=\"{opp.company}\" title=\"{opp.title}\" location=\"{opp.location}\">\n"
              f"{opp.description[:6000]}\n</posting>\n\n<template_draft>\n{draft}\n</template_draft>\n\n"
              f"Rewrite the draft in {lang} so it is specific to this posting. Return only the letter.")
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
