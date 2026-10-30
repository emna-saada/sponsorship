"""AI research with live web search (Claude + web search / web fetch).

* prospect: find companies, startups and research labs in a country that match a track,
  with their official website, careers page, LinkedIn page and any published recruiting email.
* research: for one company, confirm the website, find a published recruiting email, the
  LinkedIn page, and one concrete recent project to mention in the letter.

Every email returned must come with the URL where it is published; the tool then checks it
with the same MX verification as the rest of the pipeline. Nothing is guessed."""
import json
import re
import sys

TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]

SYSTEM = """You research employers for a final-year geomatics engineering student looking for a \
4-6 month end-of-studies internship (PFE) starting January or February 2027. Use web search and \
fetch to read official sources (the organization's own site, its careers page, its LinkedIn page). \
Report only facts you found. Never construct or guess an email address: include an email only if \
you saw it published, and give the exact URL where it appears. Prefer recruiting addresses \
(careers@, jobs@, stage@, recrutement@, hr@) and named contacts published for internships. \
Finish with a single JSON code block and nothing after it."""

COMPANY_FIELDS = """{
  "name": str, "kind": "startup" | "company" | "research lab" | "public agency",
  "country": str, "city": str, "website": str, "careers_url": str | null,
  "linkedin_url": str | null,
  "emails": [{"email": str, "source_url": str, "role": str}],
  "what_they_do": str,              // one sentence, specific to geospatial/data work
  "recent_project": str | null,     // one concrete recent project or product, with its name
  "internship_evidence": str | null // e.g. "lists PFE/stage offers on careers page", with URL
}"""


def _client(cfg):
    if not cfg.secret("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY to use AI research (console.anthropic.com).")
    import anthropic
    return anthropic, anthropic.Anthropic()


def _run(cfg, prompt: str, max_continuations: int = 4) -> str:
    anthropic, client = _client(cfg)
    messages = [{"role": "user", "content": prompt}]
    for _ in range(max_continuations + 1):
        try:
            msg = client.beta.messages.create(
                model=cfg.ai.get("model", "claude-opus-5-5"),
                max_tokens=16000,
                system=SYSTEM,
                tools=TOOLS,
                output_config={"effort": cfg.ai.get("research_effort", "medium")},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=messages,
            )
        except anthropic.APIError as e:
            print(f"  research failed: {e}", file=sys.stderr)
            return ""
        if msg.stop_reason == "pause_turn":
            # the server-side search loop paused; resend so it resumes where it stopped
            messages = [messages[0], {"role": "assistant", "content": msg.content}]
            continue
        if msg.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in msg.content if b.type == "text")
    return ""


def parse_json(text: str):
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)
    for candidate in reversed(blocks or [text]):
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            m = re.search(r"(\{.*\}|\[.*\])", candidate, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
    return None


def prospect(cfg, country: str, track, n: int = 12, exclude: list[str] = ()) -> list[dict]:
    focus = track.focus or track.label
    skip = ", ".join(sorted(exclude)[:150]) or "none"
    prompt = (f"Find {n} organizations in {country} that could host a final-year internship in {focus} "
              f"starting January/February 2027 for 4-6 months. Mix startups, established companies, "
              f"public agencies and university research labs. Related fields count too "
              f"(keywords: {', '.join(track.keywords[:25])}).\n"
              f"Skip these, already known: {skip}.\n"
              f"For each, return an object with these fields:\n{COMPANY_FIELDS}\n"
              f"Return a JSON list of the objects.")
    data = parse_json(_run(cfg, prompt))
    return [d for d in (data or []) if isinstance(d, dict) and d.get("name") and d.get("website")]


def research_company(cfg, company: str, website: str = "", country: str = "", posting_title: str = "") -> dict:
    hint = f" (website: {website})" if website else ""
    where = f" in {country}" if country else ""
    about = f" They posted: \"{posting_title}\"." if posting_title else ""
    prompt = (f"Research {company}{hint}{where}.{about} The student wants to apply for an internship "
              f"there by email and LinkedIn. Return one object with these fields:\n{COMPANY_FIELDS}")
    data = parse_json(_run(cfg, prompt))
    return data if isinstance(data, dict) else {}


def emails_from(info: dict) -> list[str]:
    """Published emails from a research result, only those with a source URL."""
    out = []
    for e in info.get("emails") or []:
        if isinstance(e, dict) and e.get("email") and str(e.get("source_url", "")).startswith("http"):
            out.append(e["email"].strip().lower())
    return out
