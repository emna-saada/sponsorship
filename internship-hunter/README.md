# Internship Hunter: geoinformatics · GIS / SIG · GeoAI · remote sensing

A personal tool that looks for **final-year (PFE / end-of-studies) internships worldwide** in
geoinformatics, GIS/SIG, GeoAI, remote sensing and spatial data. It scores each posting against
your resume, finds a **verified** recruiting email, writes a tailored cover letter, and emails
your application with your resume and cover letter attached.

```
discover ──► score vs. resume ──► enrich (find + verify email) ──► review/approve ──► send ──► report
 job APIs     keywords (EN/FR/DE/ES)   posting text, company site     you decide         SMTP      HTML dashboard
 + startups   + skills overlap         MX check, no guessed emails                      dry-run    + LinkedIn links
```

## Where opportunities come from
| Source | Coverage | Key needed |
|---|---|---|
| Arbeitnow | Europe (strong in Germany) | no |
| Remotive, Remote OK, Jobicy | Remote jobs open worldwide | no |
| Adzuna | 19 countries (UK, US, CA, AU, DE, FR, NL, BE, AT, CH, ES, IT, PL, IN, SG, NZ, ZA, BR, MX) | free key at developer.adzuna.com |
| Company career boards (Greenhouse / Lever / Ashby) | the geospatial companies in `data/companies.csv` | no |
| `data/companies.csv` (import) | 29 geospatial companies and startups (EO, GeoAI, open-source GIS) for spontaneous applications | no |
| Your own CSV | anything you find on LinkedIn, EURAXESS, your school's job board… | no |

## Setup (5 minutes)
```bash
cd internship-hunter
pip install -r requirements.txt
python -m hunter init               # creates config.toml: fill in your profile and pitch
cp ~/path/to/your_resume.pdf data/resume.pdf

export SMTP_PASSWORD="your-app-password"      # Gmail: myaccount.google.com/apppasswords (2FA required)
export ADZUNA_APP_ID=... ADZUNA_APP_KEY=...   # optional, adds 19 countries
export ANTHROPIC_API_KEY=...                  # optional, tailors each letter with Claude
```

## Daily use
```bash
python -m hunter discover                     # fetch and score postings
python -m hunter import data/companies.csv    # add the startup list as spontaneous applications
python -m hunter enrich                       # find + verify contact emails
python -m hunter review                       # approve / reject one by one (or: approve --min-score 65)
python -m hunter send                         # DRY RUN: drafts go to outbox/*.eml, check them
python -m hunter send --live                  # really send (max daily_limit per day)
python -m hunter report                       # output/opportunities.html dashboard
python -m hunter linkedin                     # LinkedIn search links + notes to paste
python -m hunter optout someone@company.com   # never contact that address again
python -m hunter stats
```

Add your own leads with a CSV shaped like `data/my_contacts_template.csv`, then
`python -m hunter import my_leads.csv`.

## How emails are found and verified
* Only **published** addresses are used: an email in the posting, or one on the company's own
  website (homepage, careers, contact, about; `robots.txt` is honored). Addresses are never guessed.
* Recruiting inboxes (`careers@`, `jobs@`, `stage@`, `recrutement@`, `hr@`, `talent@`…) are preferred
  over `info@`/`contact@`. `noreply`, `privacy`, `support`, `sales` etc. are discarded, as are
  addresses on job-board domains.
* Each address is checked for syntax, disposable domains, and that its domain has a mail server
  (MX record). An optional SMTP mailbox probe (`smtp_probe = true`) asks the server whether the
  mailbox exists; many servers refuse to answer, and home connections often block port 25.

## Safety rails (keep your mailbox out of spam folders)
* `send` is a **dry run** until you pass `--live`.
* Nothing is sent before you approve it (`review` / `approve`).
* `daily_limit` (default 15) and `seconds_between` (default 90 s) between emails.
* One email per company by default (`one_email_per_company`), and never twice to the same address.
* Each email has an unsubscribe line and `List-Unsubscribe` header; `optout` keeps a blocklist.

## About LinkedIn
LinkedIn's user agreement forbids bots that send messages or connection requests, and accounts that
use them get restricted or banned, which would hurt your search far more than it helps. So this tool
does **not** automate LinkedIn. Instead, `report` and `linkedin` give you, for every match:
internship-filtered job searches across 15 locations, a recruiter search link for the company, and a
connection note under 300 characters to paste. That takes about two minutes a day.

## Tests
```bash
pip install pytest && python -m pytest -q
```
