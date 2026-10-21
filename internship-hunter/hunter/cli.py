import argparse
import shutil
import sys
from pathlib import Path

from . import config as config_mod
from . import contacts, letters, linkedin, matching, report, sources
from .db import DB


def resume_text(cfg) -> str:
    path = cfg.path(cfg.profile.get("resume_pdf", "data/resume.pdf"))
    if not path.exists():
        return ""
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def save(cfg, db, opps) -> tuple[int, int]:
    skills = matching.resume_skills(resume_text(cfg))
    min_score = int(cfg.search.get("min_score", 45))
    new = kept = 0
    for o in opps:
        o.score, matched = matching.score(o, cfg.search, skills)
        o.matched = ",".join(dict.fromkeys(matched))
        if o.score < min_score:
            continue
        kept += 1
        new += db.upsert(o)
    return kept, new


def cmd_init(cfg_path, args):
    root = config_mod.ROOT
    target = Path(cfg_path) if cfg_path else root / "config.toml"
    if not target.exists():
        shutil.copy(root / "config.example.toml", target)
        print(f"Created {target}. Edit it, then put your resume at data/resume.pdf")
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


def cmd_enrich(cfg, db, args):
    sender, probe = cfg.email.get("smtp_user", ""), bool(cfg.email.get("smtp_probe", False))
    todo = [o for o in db.list(min_score=args.min_score) if o.status in ("new", "approved") and not o.contact_email]
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
        print(f"{o.id}  {o.score:3}  {o.status:8}  {o.company[:24]:24}  {o.title[:46]:46}  {o.contact_email or '-'}")


def cmd_review(cfg, db, args):
    for o in db.list(status="new", min_score=args.min_score):
        print(f"\n[{o.score}] {o.title} — {o.company} ({o.location})\n    {o.url}\n    email: {o.contact_email or 'none'}  matched: {o.matched}")
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


def cmd_send(cfg, db, args):
    from .mailer import Sender, build
    resume_pdf = cfg.path(cfg.profile.get("resume_pdf", "data/resume.pdf"))
    if not resume_pdf.exists():
        raise SystemExit(f"Resume not found at {resume_pdf}")
    static_cl = cfg.profile.get("static_cover_letter_pdf")
    rtext = resume_text(cfg)
    skills = matching.resume_skills(rtext)
    queue = [o for o in db.list(status="approved") if o.contact_email][: args.limit]
    if not queue:
        print("Nothing approved with a verified email. Run enrich, then review or approve.")
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
            posting_skills = [s for s in skills if matching._has(f"{o.title} {o.description}", s)]
            subject, body = letters.template_letter(cfg.profile, o, posting_skills or sorted(skills))
            body = letters.ai_letter(cfg, o, rtext, body) or body
            attachments = [resume_pdf]
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
                print(f"  sent → {o.company} <{o.contact_email}>")
            else:
                print(f"  drafted → {path}")


def cmd_optout(cfg, db, args):
    db.suppress(args.email)
    print(f"{args.email} will never be contacted.")


def cmd_report(cfg, db, args):
    path = report.build(cfg, db.list(min_score=args.min_score), cfg.output / "opportunities.html")
    print(f"Dashboard written to {path}")


def cmd_linkedin(cfg, db, args):
    p = linkedin.plan(cfg.profile, db.list(min_score=args.min_score)[: args.limit])
    print("Job searches (internship filter, newest first):")
    for q, loc, url in p["job_searches"][: args.limit]:
        print(f"  {q} @ {loc}: {url}")
    print("\nRecruiters to connect with, and a note to paste:")
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
    sub.add_parser("discover", help="fetch postings worldwide and score them")
    p = sub.add_parser("import", help="add opportunities or startups from a CSV")
    p.add_argument("csv")
    for name, h in (("enrich", "find and verify contact emails"), ("review", "approve/reject interactively"),
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
