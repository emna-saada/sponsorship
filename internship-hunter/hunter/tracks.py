"""Resume tracks: one resume (and one pitch) per specialty. Each opportunity is matched
to the track whose keywords it fits best, and that resume is the one attached."""
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .db import Opportunity


@dataclass
class Track:
    name: str
    label: str
    resume_pdf: Path
    keywords: list[str]
    pitch: str = ""
    focus: str = ""          # e.g. "LiDAR, 3D mapping or digital twins", used in letters
    queries: list[str] = field(default_factory=list)


def has(text: str, term: str) -> bool:
    # word-boundary match; short all-caps terms (GIS, SIG, PFE, AI, 3D) are case-sensitive
    # so that "sig" or "ai" inside ordinary words or slugs do not count
    if any(ord(c) >= 0x2E80 for c in term):
        return term in text  # Japanese has no spaces, so no word boundaries
    flags = 0 if (term.isupper() and len(term) <= 4) else re.I
    return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, flags) is not None


def load(cfg) -> list[Track]:
    tracks = []
    for t in cfg.raw.get("tracks", []):
        tracks.append(Track(
            name=t["name"], label=t.get("label", t["name"]), resume_pdf=cfg.path(t["resume_pdf"]),
            keywords=t.get("keywords", []), pitch=t.get("pitch", "").strip(), focus=t.get("focus", ""),
            queries=t.get("queries", []),
        ))
    if not tracks:  # single-resume setup from older configs
        tracks.append(Track(name="default", label="Resume", resume_pdf=cfg.path(cfg.profile.get("resume_pdf", "data/resume.pdf")),
                            keywords=cfg.search.get("domain_keywords", []), pitch=cfg.profile.get("pitch", "").strip(),
                            focus=cfg.profile.get("focus", "geospatial data")))
    return tracks


@lru_cache(maxsize=16)
def resume_text(path: Path) -> str:
    if not path.exists():
        return ""
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def fit(opp: Opportunity, track: Track) -> tuple[int, list[str]]:
    """Keyword fit of a posting to a track; title hits count triple."""
    hits = [k for k in track.keywords if has(f"{opp.title}\n{opp.description}", k)]
    return sum(3 if has(opp.title, k) else 1 for k in hits), hits


def choose(opp: Opportunity, tracks: list[Track]) -> Track:
    if opp.track:
        for t in tracks:
            if t.name == opp.track:
                return t
    # ties go to the first track in the config
    return max(tracks, key=lambda t: fit(opp, t)[0])
