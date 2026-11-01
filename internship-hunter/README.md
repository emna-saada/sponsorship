# Internship Hunter: GIS · Earth observation · GeoAI · LiDAR · Data science

A personal tool that finds **paid final-year (PFE) internships starting January or February 2027,
for 4 to 6 months**, in **Switzerland, Morocco, the UK, France, Japan, Saudi Arabia, Qatar and Kuwait** (plus remote roles open
to them). It works for both company and research-lab internships. It picks **the right resume for
each offer** (GIS, Geoinformatics/EO, LiDAR or Data), finds verified contacts, writes the cover
letter, and emails the application. For LinkedIn it prepares the links and notes for you.

```
discover / prospect ─► score ─► choose resume ─► enrich + research ─► review ─► send ─► report + LinkedIn
 job sites, AI web     country, paid,  by keywords    verified emails,      you      SMTP,    dashboard,
 search, CSV lists     dates, fit                     LinkedIn page, facts  decide   dry-run  notes to paste
```

## What each offer is checked for
| Check | How |
|---|---|
| Your specialty | keywords of the 4 resume tracks (GIS, EO/GeoAI, LiDAR/3D, data/ML), in English, French, German and Japanese |
| Internship | intern, stage, PFE, fin d'études, research intern, インターン… |
| Country | Switzerland, Morocco, UK, France, Japan, Saudi Arabia, Qatar, Kuwait (cities too: Lausanne, Benguerir, Harwell, Toulouse, Tsukuba, Thuwal, Doha…) |
| Paid | "unpaid" / "non rémunéré" offers are dropped; stipend, salary, gratification, CHF/£/€/円 amounts rank higher; France counts as paid (legal gratification beyond 2 months) |
| Dates | Jan/Feb 2027 and 4 to 6 months rank higher; summer and 2- or 3-month internships rank lower |
| Research or company | lab / institute / university / thesis wording, so the letter is written to a research team |
| Which resume | the track whose keywords the offer matches best; override with `python -m hunter track <id> lidar` |

## Where opportunities come from
| Source | Covers | Key |
|---|---|---|
| `prospect` (Claude + live web search) | **companies, startups and labs in every target country**, with website, careers page, LinkedIn page and published emails | `ANTHROPIC_API_KEY` |
| `data/companies.csv` | hand-picked organizations in the 8 countries (startups, agencies, research labs) | none |
| Adzuna | UK, France, Switzerland | free: developer.adzuna.com |
| Reed | UK | free: reed.co.uk/developers/jobseeker |
| France Travail | France (official API, includes stages) | free: francetravail.io |
| Remotive, Remote OK, Jobicy, Arbeitnow | remote roles and Europe | none |
| Your own CSV (`data/my_contacts_template.csv`) | anything from LinkedIn, EURAXESS, school boards… | none |

Morocco, Japan and the Gulf countries have no free job-board APIs, so `prospect` and the CSV lists do the work there.

## Setup
```bash
cd internship-hunter
pip install -r requirements.txt
python -m hunter init      # creates config.toml (or use the one prepared for you)
```
Put your four resumes in `data/` with the names used in `config.toml`.

Set your keys in the terminal (Windows: `set NAME=value`, Mac/Linux: `export NAME=value`):
```
SMTP_PASSWORD                Gmail app password (required to send)
ANTHROPIC_API_KEY            AI research + tailored letters (strongly recommended)
ADZUNA_APP_ID, ADZUNA_APP_KEY, REED_API_KEY,
FRANCETRAVAIL_CLIENT_ID, FRANCETRAVAIL_CLIENT_SECRET     optional job boards
```

## Daily use
```bash
python -m hunter discover                      # job boards
python -m hunter import data/companies.csv     # starter organizations (once)
python -m hunter prospect --n 10               # AI: 10 new orgs per country x specialty
python -m hunter enrich                        # emails from websites, verified
python -m hunter research --limit 20           # AI: published emails, LinkedIn page, a recent project
python -m hunter report                        # output/opportunities.html
python -m hunter review                        # approve / reject
python -m hunter send                          # DRY RUN to outbox/, check the drafts
python -m hunter send --live                   # really send (max 15 per day)
python -m hunter linkedin                      # LinkedIn links + notes
```
`prospect` also takes `--country japan` and `--track lidar` to focus one search.

## How emails are found and verified
* Only **published** addresses: in the posting, on the organization's own website (`robots.txt`
  honored), or found by the AI research step **with the URL where it is published**. No guessing.
* Recruiting inboxes (`careers@`, `jobs@`, `stage@`, `recrutement@`, `hr@`…) are preferred; `noreply`,
  `privacy`, `support`, `sales` and job-board domains are discarded.
* Every address must have a working mail server (MX record).

## Never contacting the same organization twice
* Before every `send --live`, the tool reads your **Gmail Sent folder** (last 12 months) and records
  every address you wrote to, by this tool or by hand. If it cannot read it, nothing is sent.
* It then skips any address already emailed, any address at an organization's domain already
  emailed (e.g. `jobs@` after `careers@` at the same company), and any organization with the same name.
  Public providers (gmail.com, outlook.com…) only block the exact address.
* `hunter.db` also keeps this history. Keep it; if it is lost, the Gmail check rebuilds it.
* `python -m hunter contacted` lists everyone already contacted; `python -m hunter sync-sent` runs the
  Gmail check on its own.

## Safety rails
Dry run until `--live`; nothing is sent before you approve it; 15 emails a day, 90 s apart; unsubscribe
line and `optout` blocklist.

## LinkedIn
LinkedIn's user agreement forbids bots that send messages or connection requests, and those accounts
get restricted, so this tool never automates LinkedIn. For each offer you get the organization's LinkedIn
page (found by `research`) or a people search (recruiters for companies, researchers for labs), plus a
connection note under 300 characters to paste. Internship-filtered job searches are prepared for each
target country.

## Tests
```bash
pip install pytest && python -m pytest -q
```
