"""Self-contained HTML dashboard of every opportunity found, worldwide."""
import html
from datetime import date
from pathlib import Path

from . import linkedin

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Internship Opportunities</title>
<style>
:root{{--bg:#f7f8fa;--card:#fff;--ink:#16202c;--muted:#5d6b7a;--line:#e3e7ec;--acc:#0b7a5f;--chip:#e8f3ef}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1419;--card:#172029;--ink:#e6edf3;--muted:#93a1b0;--line:#26323d;--acc:#3ccf9f;--chip:#183429}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1150px;margin:auto;padding:24px 16px}}h1{{margin:0 0 4px;font-size:24px}}.muted{{color:var(--muted)}}
.bar{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}}input,select{{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit}}
input{{flex:1;min-width:200px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}}
.top{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}}.t{{font-weight:600}}a{{color:var(--acc)}}
.score{{font-weight:700;font-variant-numeric:tabular-nums}}.chip{{display:inline-block;background:var(--chip);border-radius:99px;padding:1px 8px;margin:4px 4px 0 0;font-size:12px}}
.links a{{margin-right:14px;font-size:14px}}details{{margin-top:6px}}textarea{{width:100%;font:inherit;font-size:13px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}}
.stats{{display:flex;gap:18px;flex-wrap:wrap}}.stats b{{font-size:20px;display:block}}
</style></head><body><main>
<h1>Geoinformatics internship opportunities</h1>
<div class="muted">Updated {today} · {n} matches · sources: {sources}</div>
<div class="stats" style="margin-top:14px">{stats}</div>
<div class="bar"><input id="q" placeholder="Filter: country, company, keyword…"><select id="st"><option value="">All statuses</option>{status_opts}</select></div>
<div id="list">{cards}</div>
<h2 style="margin-top:32px">LinkedIn searches (click, then apply or message yourself)</h2>
<p class="muted">LinkedIn bans automated messaging, so these are prepared for you to open by hand.</p>
{li}
<p class="muted" style="margin-top:28px">Remote listings include data from Remote OK, Remotive, Jobicy and Arbeitnow; follow each link to the original posting.</p>
</main><script>
const q=document.getElementById('q'),st=document.getElementById('st');
function f(){{const v=q.value.toLowerCase(),s=st.value;document.querySelectorAll('.card').forEach(c=>{{c.style.display=(c.dataset.k.includes(v)&&(!s||c.dataset.s===s))?'':'none'}})}}
q.oninput=f;st.onchange=f;
</script></body></html>"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def build(cfg, opportunities, path: Path) -> Path:
    cards, statuses, sources = [], {}, set()
    for o in opportunities:
        statuses[o.status] = statuses.get(o.status, 0) + 1
        sources.add(o.source.split("-")[0])
        chips = "".join(f'<span class="chip">{_e(m)}</span>' for m in (o.matched or "").split(",")[:8] if m)
        email = (f'<a href="mailto:{_e(o.contact_email)}">{_e(o.contact_email)}</a> ({_e(o.email_status)})'
                 if o.contact_email else f'<span class="muted">no verified email{": " + _e(o.email_status) if o.email_status else ""}</span>')
        note = linkedin.connection_note(cfg.profile, o.company, o.title)
        key = f"{o.title} {o.company} {o.location} {o.source} {o.matched}".lower()
        cards.append(f"""<div class="card" data-k="{_e(key)}" data-s="{_e(o.status)}">
<div class="top"><div><div class="t">{_e(o.title)}</div><div>{_e(o.company)} · <span class="muted">{_e(o.location) or "Location not given"}</span></div></div>
<div><span class="score">{o.score}</span><span class="muted">/100 · {_e(o.status)}</span></div></div>
<div>{chips}</div>
<div class="links" style="margin-top:8px">{f'<a href="{_e(o.url)}" target="_blank" rel="noopener">Posting / apply</a>' if o.url else ''}
{f'<a href="{_e(o.company_website)}" target="_blank" rel="noopener">Company website</a>' if o.company_website else ''}
<a href="{_e(linkedin.people_search_url(o.company))}" target="_blank" rel="noopener">Recruiters on LinkedIn</a>
<span>Email: {email}</span></div>
<details><summary class="muted">LinkedIn note to paste</summary><textarea rows="3" readonly>{_e(note)}</textarea></details>
</div>""")
    li_rows = []
    for q in linkedin.JOB_QUERIES:
        links = " · ".join(f'<a href="{_e(linkedin.job_search_url(q, loc))}" target="_blank" rel="noopener">{_e(loc)}</a>'
                           for loc in linkedin.LOCATIONS)
        li_rows.append(f'<div class="card"><div class="t">{_e(q)}</div><div class="links">{links}</div></div>')
    stats = "".join(f'<div><b>{v}</b><span class="muted">{_e(k)}</span></div>' for k, v in sorted(statuses.items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGE.format(
        today=date.today().isoformat(), n=len(opportunities), sources=_e(", ".join(sorted(sources)) or "none yet"),
        stats=stats, status_opts="".join(f'<option>{_e(s)}</option>' for s in sorted(statuses)),
        cards="".join(cards) or '<p class="muted">No matches yet. Run discover.</p>', li="".join(li_rows),
    ), encoding="utf-8")
    return path
