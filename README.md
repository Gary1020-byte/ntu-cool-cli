# ntu-cool-cli

Read-only command-line access to NTU Cool: course announcements, course
files, CA handouts, and submission status.

> 中文版: [README.zh-TW.md](README.zh-TW.md)

One CLI, four stores. Cool keeps a course's material in more than one place, and
the obvious one is often empty:

| what you want | where it actually is |
|---|---|
| what a course announced | `discussion_topics` — announcements and their attachments |
| course files: handouts, worksheets, solutions, syllabus | the Files tree (`folders`) |
| a CA handout, when the Files tree looks empty | the **assignment description** (`assignments`) |
| lectures grouped by week | **modules** (`modules` → `modules/{id}/items`) |
| whether your submission was accepted | `/submissions/self` |

```bash
# no credentials — is the platform reachable?
python3 scripts/ntu_fetch.py --probe

# what courses am I taking this term?
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
```

**Read-only.** It logs in to read and never writes, posts, or comments on
cool.ntu.edu.tw.

---

## Why not a service

A daemon that polls on a schedule and pushes to Telegram needs a persistent
store, an ORM, and a migration surface — to answer a one-endpoint question.
On Python 3.14 that stack fails three ways before it reaches the endpoint:

```
ImportError: cannot import name 'Markup' from 'jinja2'          # Flask 1.0.2
AttributeError: module 'sqlite3.dbapi2' has no attribute 'version_info'   # SQLAlchemy 1.3.8
TypeError: Mapper.__init__() got an unexpected keyword argument 'order_by'
```

Upgrading Flask cascades into the SQLAlchemy break, which cascades into a
mapper-API removal. The total patch surface is one file and four lines — which
tells you the service is the problem, not the pins.

This script drops Flask, SQLAlchemy, and `beautifulsoup4` entirely. **The only
third-party import is `requests`.** HTML parsing uses `html.parser` from the
stdlib, because the two things needed from BeautifulSoup — "find a form, read
its inputs" and "flatten visible text" — are twenty lines of `HTMLParser`.

Fetching is also the honest scope: a script that reads and exits has nothing to
keep in sync. Storage, dedupe, and delivery belong to whatever runs it.

---

## Install

As a command — this gives you `ntu-cool-cli` on your PATH:

```bash
git clone https://github.com/Gary1020-byte/ntu-cool-cli.git
cd ntu-cool-cli
pipx install .          # or: uv tool install .  /  python3 -m pip install --user .
ntu-cool-cli --probe
```

The module is `ntu_fetch`, the command is `ntu-cool-cli`, and both do exactly the
same thing — `ntu-cool-cli --help` and `python3 scripts/ntu_fetch.py --help` are
identical. Use whichever suits; the script needs no install at all.

Requires Python 3.9+ and `requests`. Verify:

```bash
ntu-cool-cli --probe
```

### Tests

```bash
python3 -m unittest discover -s tests -v
```

52 offline tests, no network and no credentials. They cover the JSON prefix
handling, HTML form extraction without BeautifulSoup, the credential-file
permission guard, and — the one that matters — that a trap form parked in
`<head>` can never become a POST target.

Two classes guard the bug that was silently losing files: one drives
`_paged_get` across a multi-page Link chain, one proves the walk enters through
the root and still works when `/folders/root` answers 403.

### Note

The console script is a thin wrapper: `ntu_fetch:main`, with `main()` returning
the exit code. Importing the module has no side effects, so the tests can import
it without logging in or reaching the network.

> **Test with the interpreter you will actually use.** A virtualenv's Python and the
> system Python have separate `site-packages`. A bug report that says "the import
> fails" is often a report about the wrong interpreter.
> See `references/testing-and-interpreters.md`.

---

## Credentials

Two platforms need your NTU account. **This tool never stores, requests, or prints a
password.**

Either export them for one shell:

```bash
export NTU_USER=bXXXXXXXX
export NTU_PASS='...'
```

…or, better, keep them in a file the script will only read when it is mode `600`:

```bash
umask 077
echo '{"ntu_user":"bXXXXXXXX","ntu_pass":"..."}' > ~/.ntu-creds.json
```

A group- or world-readable credential file is **refused** with the `chmod` command to
fix it. Note that environment variables exported in one terminal are not visible to
another — a credential file is what makes this script usable unattended (cron, etc.).

### Where the password can and cannot leak

The password is submitted to ADFS as a form field. Four things it could have
done, and what it actually does:

| leak surface | what the tool does |
|---|---|
| printed in an error message | it doesn't — the login failure names the hop and the HTTP status, never the submitted values |
| dumped by `requests` debug logging | it doesn't — `enable_http_debugging()` and `debuglevel` are absent, and a test asserts they stay absent |
| left in the output as a traceback | it doesn't — the traceback would carry the *call*, not the value; the value only ever exists in the POST body |
| sitting in a world-readable file | it refuses to read one |

**The real risks are on your side of the boundary:**

- **The credential file's path.** `--cred-file ~/.ntu-creds.json` goes into
  your shell history, and the path is visible in the process list. That is
  why the environment-variable path is the better one when you are typing
  the command by hand — and the file path is the better one when a cron job
  needs it unattended.
- **The signed download URLs.** A file's `url` from the API authenticates.
  The tool never logs one, and it never writes one into a file it produces.
  Don't paste one into an issue.
- **The session cookies.** They live in the `requests.Session` for the length
  of the run and are gone when the process exits. Nothing is written to disk.

---

## The three traps this encodes

### 1. `/api/v1/courses` is not your current course list

It returns courses the account has **ever** been enrolled in.

```
API said:      10 courses, newest announcement 2026-10-13, oldest 2025-09-05
               → omitted 3 current-term courses, one of them your main math course
               → included 3 dead courses as {"access_restricted_by_date": true}

Home page says: 7 courses, term "<term>"  ← correct
```

`fetch_courses()` parses the roster out of the home page's embedded JSON. The
historical list is still reachable via `fetch_all_courses_historical()` when you want
last term's exam schedule — never as the current roster.

### 2. Course material is not in the announcement body

Measured on one term:

```
20 announcement bodies    2,041 characters   0 file links
course Files tree         91 files
announcement attachments   5 files           <- a third set
```

An announcement whose entire body is the word `attached` is **not** a missing-
attachment case to report — it is the normal shape, and the files are fully
retrievable. Reporting "this course has no attachments" after reading announcements
alone reads as complete and misses every worksheet.

### 3. Enter through the root, and follow `Link` — three separate traps

```
GET /api/v1/courses/{id}/folders/root   → the root folder        <- enter here
folder["files_url"]                     → files in that folder   (paginated)
folder["folders_url"]                   → child folders; recurse (paginated)
```

**(a) The URLs come off the objects.** Six plausible spellings return 404 or 400 —
including `/api/v1/courses/{id}/files`, which looks obviously right and is dead.

**(b) `/folders` is a flat list, not a tree.** It enumerates folders at every depth.
Iterating it *and* recursing `folders_url` walks each non-root folder twice — three
times when its parent is listed too. A naive walk reported **110 files where 64 were
retrievable**. Enter through the root instead.

**(c) Every list endpoint is paginated at 10 by default.** This is the trap that
actually loses data: a folder holding 29 files returns 10, with no error and no
empty-looking tail. Measured across one term — **27 of 91 files silently missing**.

```
projected from Link header:  <...>; rel="next", <...>; rel="last"
bare request:                page=1&per_page=10
```

Follow `Link: rel="next"`. Do not "fix" it with a bigger `per_page` — the API caps
that parameter, and the Link header is the only pagination contract it honours.

`fetch_course_files()` enters through `/folders/root` (falling back to the
parentless entries of `/folders`, because `/folders/root` answers **403** on at
least one non-credit course), paginates both directions, and dedupes by file `id`
as a last resort. There are tests that fail if any of the three is removed.

Announcement attachments are a **third** set, separate from both: one term had 5 of
them and 91 in the Files tree. `--list-files` and `--download-files` collect both.

---

## Usage

### Announcements

```bash
# current term roster
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json

# one course's announcements to stdout
python3 scripts/ntu_fetch.py --course <COURSE> --since 2026-09-01 --stdout

# write markdown into a notes directory
python3 scripts/ntu_fetch.py --course <COURSE> --since 2026-09-01 --out ./captures/
```

### Course files

```bash
# list everything in the Files tree
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json

# download, skipping anything over 20 MB
python3 scripts/ntu_fetch.py --download-files --course <COURSE> \
    --cred-file ~/.ntu-creds.json --files-out ./files/ --max-mb 20
```

Downloads land at `<files-out>/<course_id>/<file_id>/<filename>`, so two files with
the same display name never collide.

### Assignments, submissions, pages, modules

```bash
# the homework roster: name, due_at, lock_at, points
python3 scripts/ntu_fetch.py --list-assignments --course <COURSE> --cred-file ~/.ntu-creds.json

# your own submission status per assignment (read-only)
python3 scripts/ntu_fetch.py --list-submissions --course <COURSE> --cred-file ~/.ntu-creds.json

# course pages: syllabus, calendar, late-submission policy
python3 scripts/ntu_fetch.py --list-pages --course <COURSE> --cred-file ~/.ntu-creds.json

# modules — lectures grouped by week
python3 scripts/ntu_fetch.py --list-modules --course <COURSE> --cred-file ~/.ntu-creds.json

# handout links that live in assignment descriptions, not the Files tree
python3 scripts/ntu_fetch.py --list-handouts --course <COURSE> --cred-file ~/.ntu-creds.json

# one course page's content, by slug (see --list-pages for the slugs)
python3 scripts/ntu_fetch.py --show-page ke-cheng-da-gang --course <COURSE> \
    --cred-file ~/.ntu-creds.json

# download the handouts themselves
python3 scripts/ntu_fetch.py --download-handout --course <COURSE> \
    --cred-file ~/.ntu-creds.json --files-out ./handouts/
```

`lock_at` is the real deadline; `due_at` is the nominal one, and the gap between
them is the buffer the course page promises. A `lock_at` in the past means the
upload window is closed.

`--show-page` needs exactly one course — it prints the page's title, its URL,
and the body as plain text. `--download-handout` follows the two-hop path
(the endpoint answers with JSON describing the file; the signed URL is inside
it) and writes the file under its real display name.

---

## Installing this as an agent skill

Copy the block below into your agent (Claude Code, Hermes, a custom assistant —
anything that can run a command and read a file).

**The agent must ask which capabilities are needed, then install only those.**
Each capability maps to a specific flag or a specific section of `SKILL.md`, so
a partial install is the normal case, not a compromise.

````text
Install the NTU Cool skill: https://github.com/Gary1020-byte/ntu-cool-cli

Before installing anything, ask me which capabilities I need. Do NOT install
all of them by default. The capabilities are:

  1. Announcements        — course announcements, deadlines, TA notices
                            flag: --course / --all-courses
  2. Course files         — the Files tree: handouts, worksheets, solutions,
                            syllabus PDFs
                            flags: --list-files, --download-files
  3. Announcement attachments — files bound to one announcement (a separate,
                            smaller set from the Files tree)
                            included in --list-files / --download-files
  4. Homework roster      — /assignments: what is assigned, due_at, lock_at,
                            points, and the handout link
                            flag: --list-assignments
  5. Submission status    — my own submission per assignment: unsubmitted /
                            submitted / graded, score, late policy
                            flag: --list-submissions
  6. Course pages         — syllabus, calendar, late-submission policy,
                            submission instructions
                            flag: --list-pages
  7. Modules              — lectures grouped by week
                            flag: --list-modules
  8. CA handouts          — handout links that live in assignment descriptions
                            rather than the Files tree (the Files tree is often
                            nearly empty for CA courses)
                            flags: --list-handouts, --download-handout
  9. Page content         — the body of one course page: syllabus, calendar,
                            late-submission policy, submission instructions
                            flag: --show-page <slug>

Show me this list, ask which ones I want, and wait for my answer.

Then:
  - clone the repo
  - install the `ntu-cool-cli` package
  - read SKILL.md, and keep only the sections matching the capabilities I chose
  - tell me how to supply credentials. Prefer the environment variables
    NTU_USER and NTU_PASS — nothing lands on disk and nothing stays in the
    shell history. The alternative is a JSON file with ntu_user / ntu_pass
    keys, passed with --cred-file; that file must be mode 600, because the
    tool refuses to read a world-readable one. Never write credentials into
    the repo, and never echo them back to me.
  - run `ntu-cool-cli --probe` first. It needs no credentials and tells you
    whether the platform is reachable. Do not debug credentials until the
    probe is clean.

This tool is READ-ONLY. It logs in to read and never writes, posts, or
comments on cool.ntu.edu.tw. It cannot upload a submission — if I need to
hand something in, tell me what is due and where the file is, and let me do
the upload in the browser. Never attempt a write against the platform.
````

### Why the agent should ask first

Cool keeps a course's material in four different places, and which one holds
what is not guessable from the outside — the Files tree is nearly empty for
some CA courses, and a handout that is missing from it is usually in the
assignment description. Installing all nine capabilities means the agent
reads a skill file that describes stores it will never query, and every
capability it does not need is a way for it to answer a question with the
wrong source.

The list also doubles as a map: an agent that knows "the Files tree is empty
for this course" knows to ask for `--list-handouts` instead of reporting
"no attachments".

---

## What the output is worth trusting

| claim | status |
|---|---|
| NTU Cool endpoints still exist | verified — 401 + structured body, not 404 |
| the SAML login sequence | verified against the live site |
| `/api/v1/courses` as current roster | **false** — see trap 1 |
| the Files-tree endpoint shape | verified, 91 files enumerated across a term |
| downloads are really PDFs | magic-checked per file |
| nothing is silently dropped | verified — pagination followed via `Link` |
| Ceiba reachability | **varies by network** — see `references/ceiba-unreachable.md` |
| Ceiba scraping | not implemented; the positional table parser is unverified |

**A download reporting `OK` has passed both checks.** Cool answers an expired signed
URL with HTTP 200 carrying the login page, so status code alone proves nothing —
the script sniffs for `<!DOCTYPE html` and verifies `%PDF-` against the declared
content type.

Signed file URLs are credential-bearing. The script never logs them; don't paste them
anywhere.

---

## Many course PDFs have no text layer

Of 10 files in one course, **9 had a zero-length text layer** — they are rasterised
scans or vector drawings. That is not data loss. Render at ~160 dpi and read the
image:

```python
import pymupdf
d = pymupdf.open("worksheet.pdf")
d[0].get_pixmap(dpi=160).save("page1.png")   # then read it
```

Never file a PDF as unusable on the strength of one extraction path.

---

## Ceiba

`ceiba.ntu.edu.tw` is not implemented. On some networks it is unreachable (DNS
resolves, three sibling NTU hosts answer in <150 ms, ceiba times out on connect).
That is a network-access question, not a code one — see
`references/ceiba-unreachable.md` for the control test that distinguishes them.

---

## Files

```
SKILL.md                              the rulebook: verification status, traps, workflow
scripts/ntu_fetch.py                  the whole tool
pyproject.toml                        makes `ntu-cool-cli` installable
tests/test_ntu_fetch.py               52 offline tests, no network
ACKNOWLEDGEMENTS.md                   attribution and licensing notes
references/api-findings.md           what the platform actually returns
references/ceiba-unreachable.md       reachability control test
references/testing-and-interpreters.md  the venv-vs-system-python trap
```

`SKILL.md` is written for an AI agent reading it before acting. It is readable by
humans too, but its shape is "what is verified, what is not, what will bite you".

---

## Ethics and scope

Read-only. Every request this script makes is a `GET` except the two login form
submissions required to obtain a session — there is no upload, no write, no delete,
and no course modification of any kind. It obeys the same rule as the account
holder: fetch what you can already see by logging in, and nothing more.

Use it against your own account.