import argparse
import shutil
import sys
from pathlib import Path

from . import config as config_mod
from . import contacts, geo, letters, linkedin, matching, report, research, sources, tracks as tracks_mod
from .db import DB, Opportunity


def load_tracks(cfg):
    ts = tracks_mod.load(cfg)
    skills = {t.name: matching.resume_skills(tracks_mod.resume_text(t.resume_pdf)) for t in ts}
    return ts, skills


def classify(cfg, o: Opportunity, ts, skills) -> int:
    """Fills country, kind, pay, track and score on an opportunity; returns the score."""
    o.country = o.country or geo.country(o.location, o.description)
    o.kind = o.kind or matching.kind(o)
    o.pay = matching.pay_status(o)
    o.score, matched, best = matching.score(o, cfg.search, ts, skills)
    o.track = o.track or best
    o.matched = ",".join(dict.fromkeys(matched))
    return o.score


def save(cfg, db, opps) -> tuple[int, int]:
    ts, skills = load_tracks(cfg)
    min_score = int(cfg.search.get("min_score", 45))
    new = kept = 0
    for o in opps:
        if classify(cfg, o, ts, skills) < min_score:
            continue
        kept += 1
        new += db.upsert(o)
    return kept, new


def cmd_init(cfg_path, args):
    root = config_mod.ROOT
    target = Path(cfg_path) if cfg_path else root / "config.toml"
    if not target.exists():
        shutil.copy(root / "config.example.toml", target)
        print(f"Created {target}. Edit it, then put your resumes in data/")
    else:
        print(f"{target} already exists")


def cmd_discover(cfg, db, args):
    print("Fetching postings…")
    kept, new = save(cfg, db, sources.fetch_all(cfg))
    print(f"{kept} postings match your profile, {new} are new.")


def cmd_import(cfg, db, args):
    opps = sources.import_csv(Path(args.csv))
    kept, new = save(cfg, db, opps)
    print(f"Imported {len(opps)} rows: {kept} match, {new} new.")


def cmd_prospect(cfg, db, args):
    """AI + web search: find organizations per country and track, add them as spontaneous leads."""
    ts, _ = load_tracks(cfg)
    countries = [args.country] if args.country else cfg.search.get("target_countries", [])
    chosen = [t for t in ts if not args.track or t.name == args.track]
    known = {o.company.lower() for o in db.list()}
    for country in countries:
        for t in chosen:
            print(f"Searching {geo.LABELS.get(country, country)} for {t.label} hosts…")
            found = research.prospect(cfg, geo.LABELS.get(country, country), t, args.n, sorted(known))
            opps = []
            for d in found:
                if d["name"].lower() in known:
                    continue
                known.add(d["name"].lower())
                emails = research.emails_from(d)
                desc = " ".join(str(d.get(k) or "") for k in ("what_they_do", "recent_project", "internship_evidence"))
                opps.append(Opportunity(
                    title="Final-year internship (spontaneous application)", company=d["name"],
                    location=f"{d.get('city') or ''}, {d.get('country') or geo.LABELS.get(country, country)}".strip(", "),
                    url="", description=f"{desc} {' '.join(t.keywords[:3])}", company_website=d.get("website", ""),
                    contact_email=emails[0] if emails else "", source="prospect", track=t.name,
                    country=country, kind="research" if "lab" in str(d.get("kind", "")).lower() or "universit" in desc.lower() else "professional",
                    company_linkedin=d.get("linkedin_url") or "", insight=d.get("recent_project") or "",
                    note=d.get("careers_url") or "",
                ))
            kept, new = save(cfg, db, opps)
            print(f"  {len(found)} found, {new} new leads")


def cmd_research(cfg, db, args):
    """AI + web search: confirm website, LinkedIn page, published email and a recent project."""
    todo = [o for o in db.list(min_score=args.min_score) if o.status in ("new", "approved")
            and (args.all or not o.contact_email or not o.insight)][: args.limit]
    print(f"Researching {len(todo)} organizations (uses your Anthropic API credit)…")
    for o in todo:
        info = research.research_company(cfg, o.company, o.company_website, geo.LABELS.get(o.country, ""), o.title)
        if not info:
            print(f"  {o.company[:30]:30} nothing found")
            continue
        fields = {}
        if info.get("website") and not o.company_website:
            fields["company_website"] = info["website"]
        if info.get("linkedin_url"):
            fields["company_linkedin"] = info["linkedin_url"]
        if info.get("recent_project"):
            fields["insight"] = info["recent_project"]
        if not o.contact_email:
            for e in research.emails_from(info):
                status = contacts.verify(e, cfg.email.get("smtp_user", ""), bool(cfg.email.get("smtp_probe", False)))
                if status in ("valid", "accept-unknown"):
                    fields.update(contact_email=e, email_status=f"{status} (published)")
                    break
        if fields:
            db.update(o.id, **fields)
        print(f"  {o.company[:30]:30} {fields.get('contact_email', o.contact_email) or '-':36} "
              f"{'LinkedIn ✓' if fields.get('company_linkedin') else ''}")


def cmd_enrich(cfg, db, args):
    sender, probe = cfg.email.get("smtp_user", ""), bool(cfg.email.get("smtp_probe", False))
    todo = [o for o in db.list(min_score=args.min_score) if o.status in ("new", "approved") and not o.email_status]
    print(f"Looking for verified emails for {len(todo)} opportunities…")
    found = 0
    for o in todo:
        email, status = contacts.find_contact(o, sender, probe)
        db.update(o.id, contact_email=email, email_status=status)
        found += bool(email)
        print(f"  {o.company[:30]:30} {email or '-':38} {status}")
    print(f"{found} verified emails found.")


def cmd_list(cfg, db, args):
    for o in db.list(status=args.status, min_score=args.min_score)[: args.limit]:
        print(f"{o.id}  {o.score:3}  {o.status:8}  {geo.LABELS.get(o.country, o.country)[:11]:11}  "
              f"{o.track[:14]:14}  {o.pay[:7]:7}  {o.company[:22]:22}  {o.title[:40]:40}  {o.contact_email or '-'}")


def cmd_review(cfg, db, args):
    for o in db.list(status="new", min_score=args.min_score):
        print(f"\n[{o.score}] {o.title} — {o.company} ({o.location})\n"
              f"    {geo.LABELS.get(o.country, o.country)} · {o.kind} · pay: {o.pay} · resume: {o.track}\n"
              f"    {o.url or o.company_website}\n    email: {o.contact_email or 'none'}  matched: {o.matched}")
        ans = input("  approve (a) / reject (r) / skip (s) / quit (q)? ").strip().lower()
        if ans == "q":
            break
        if ans in ("a", "r"):
            db.update(o.id, status="approved" if ans == "a" else "rejected")


def cmd_approve(cfg, db, args):
    ids = args.ids or [o.id for o in db.list(status="new", min_score=args.min_score) if o.contact_email]
    for i in ids:
        db.update(i, status="approved")
    print(f"Approved {len(ids)}.")


def cmd_reject(cfg, db, args):
    for i in args.ids:
        db.update(i, status="rejected")


def cmd_track(cfg, db, args):
    """Force which resume an opportunity gets."""
    names = [t.name for t in tracks_mod.load(cfg)]
    if args.track not in names:
        raise SystemExit(f"Unknown track. Choose one of: {', '.join(names)}")
    db.update(args.id, track=args.track)


def cmd_send(cfg, db, args):
    from .mailer import Sender, build
    ts, skills = load_tracks(cfg)
    missing = [str(t.resume_pdf) for t in ts if not t.resume_pdf.exists()]
    if missing:
        raise SystemExit("Resume not found: " + ", ".join(missing))
    static_cl = cfg.profile.get("static_cover_letter_pdf")
    queue = [o for o in db.list(status="approved") if o.contact_email][: args.limit]
    if not queue:
        print("Nothing approved with a verified email. Run enrich/research, then review or approve.")
        return
    mode = "LIVE" if args.live else "DRY RUN (writing to outbox/; add --live to send)"
    print(f"{mode}: {len(queue)} applications")
    with Sender(cfg, db, args.live) as sender:
        for o in queue:
            reason = sender.can_send(o.contact_email)
            if reason:
                print(f"  skip {o.company}: {reason}")
                if reason == "daily limit reached":
                    break
                continue
            track = tracks_mod.choose(o, ts)
            overlap = matching.posting_skills(o, skills[track.name])
            subject, body = letters.template_letter(cfg.profile, o, overlap or sorted(skills[track.name])[:5], track)
            body = letters.ai_letter(cfg, o, tracks_mod.resume_text(track.resume_pdf), body) or body
            attachments = [track.resume_pdf]
            if static_cl:
                attachments.append(cfg.path(static_cl))
            else:
                safe = "".join(c for c in o.company if c.isalnum())[:40] or "company"
                attachments.append(letters.to_pdf(body, cfg.output / "letters" / f"Cover_Letter_{safe}.pdf", cfg.profile))
            msg = build(cfg, o.contact_email, subject, body, attachments)
            try:
                path = sender.send(msg, o.id)
            except Exception as e:  # keep going: one bad address must not stop the batch
                db.update(o.id, status="failed", note=str(e)[:200])
                print(f"  FAILED {o.company}: {e}")
                continue
            if args.live:
                db.update(o.id, status="sent")
                print(f"  sent → {o.company} <{o.contact_email}> with {track.resume_pdf.name}")
            else:
                print(f"  drafted → {path.name} ({track.resume_pdf.name})")


def cmd_optout(cfg, db, args):
    db.suppress(args.email)
    print(f"{args.email} will never be contacted.")


def cmd_report(cfg, db, args):
    path = report.build(cfg, db.list(min_score=args.min_score), cfg.output / "opportunities.html")
    print(f"Dashboard written to {path}")


def cmd_linkedin(cfg, db, args):
    p = linkedin.plan(cfg, db.list(min_score=args.min_score)[: args.limit])
    print("Job searches (internship filter, newest first):")
    for q, loc, url in p["job_searches"]:
        print(f"  {q} @ {loc}: {url}")
    print("\nPeople to connect with, and a note to paste:")
    for company, title, url, note in p["people"]:
        print(f"\n  {company} — {title}\n  {url}\n  note: {note}")


def cmd_stats(cfg, db, args):
    for k, v in sorted(db.stats().items()):
        print(f"{k:10} {v}")
    print(f"sent today: {db.sent_today()} / {cfg.email.get('daily_limit', 15)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hunter", description="Geoinformatics internship hunter")
    ap.add_argument("--config", help="path to config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create config.toml")
    sub.add_parser("discover", help="fetch postings from job sites and score them")
    p = sub.add_parser("import", help="add opportunities or organizations from a CSV")
    p.add_argument("csv")
    p = sub.add_parser("prospect", help="AI web search for companies, startups and labs per country")
    p.add_argument("--country", help="one of target_countries (default: all)")
    p.add_argument("--track", help="one resume track (default: all)")
    p.add_argument("--n", type=int, default=10, help="organizations per country and track")
    p = sub.add_parser("research", help="AI web search for emails, LinkedIn page and recent work")
    p.add_argument("--min-score", type=int, default=55)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--all", action="store_true", help="also re-research ones that already have details")
    for name, h in (("enrich", "find and verify contact emails on websites"), ("review", "approve/reject interactively"),
                    ("report", "write the HTML dashboard"), ("linkedin", "print LinkedIn links and notes")):
        p = sub.add_parser(name, help=h)
        p.add_argument("--min-score", type=int, default=0)
        p.add_argument("--limit", type=int, default=30)
    p = sub.add_parser("list", help="show stored opportunities")
    p.add_argument("--status")
    p.add_argument("--min-score", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("approve", help="approve ids, or all new ones with an email above --min-score")
    p.add_argument("ids", nargs="*")
    p.add_argument("--min-score", type=int, default=60)
    p = sub.add_parser("reject")
    p.add_argument("ids", nargs="+")
    p = sub.add_parser("track", help="choose which resume an opportunity gets")
    p.add_argument("id")
    p.add_argument("track")
    p = sub.add_parser("send", help="send approved applications (dry run unless --live)")
    p.add_argument("--live", action="store_true")
    p.add_argument("--limit", type=int, default=15)
    p = sub.add_parser("optout", help="never contact this address again")
    p.add_argument("email")
    sub.add_parser("stats")
    args = ap.parse_args(argv)

    if args.cmd == "init":
        return cmd_init(args.config, args)
    cfg = config_mod.load(args.config)
    db = DB(cfg.db_path)
    try:
        globals()[f"cmd_{args.cmd}"](cfg, db, args)
    except KeyboardInterrupt:
        sys.exit(130)
