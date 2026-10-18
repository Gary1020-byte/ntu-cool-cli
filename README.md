# ntu-course-announcements

Fetch NTU Cool course announcements and course files from the command line.

> 中文版: [README.zh-TW.md](README.zh-TW.md)

Built after reading [`brianbbsu/NTU-Announcement-Crawler`](https://github.com/brianbbsu/NTU-Announcement-Crawler)
and finding it unusable on a modern Python. Reimplemented as a single
~700-line script with **one** third-party dependency.

```bash
# no credentials — is the platform reachable?
python3 scripts/ntu_fetch.py --probe

# what courses am I taking this term?
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
```

---

## Why not just use the upstream crawler

That project targets a 2019 interpreter and carries a Flask + SQLAlchemy + ORM
service to answer a one-endpoint question. On Python 3.14 it fails three ways:

```
ImportError: cannot import name 'Markup' from 'jinja2'          # Flask 1.0.2
AttributeError: module 'sqlite3.dbapi2' has no attribute 'version_info'   # SQLAlchemy 1.3.8
TypeError: Mapper.__init__() got an unexpected keyword argument 'order_by'
```

Upgrading Flask cascades into the SQLAlchemy break, which cascades into a mapper-API
removal. The total patch surface is one file and four lines — which tells you the
service is the problem, not the pins.

This script drops Flask, SQLAlchemy, and `beautifulsoup4` entirely. **The only
third-party import is `requests`.** HTML parsing uses `html.parser` from the stdlib,
because the two things needed from BeautifulSoup — "find a form, read its inputs"
and "flatten visible text" — are twenty lines of `HTMLParser`.

None of this is a fork. The upstream repo has no LICENSE file, so it cannot be
redistributed — nothing was copied from it, and what was learned from reading its
source is credited in [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).

---

## Install

As a command — this gives you `ntu-cool` on your PATH:

```bash
git clone <this-repo>
cd ntu-cool-announcements-skill
pipx install .          # or: uv tool install .  /  python3 -m pip install --user .
ntu-cool --probe
```

The module is `ntu_fetch`, the command is `ntu-cool`, and both do exactly the
same thing — `ntu-cool --help` and `python3 scripts/ntu_fetch.py --help` are
identical. Use whichever suits; the script needs no install at all.

Requires Python 3.9+ and `requests`. Verify:

```bash
ntu-cool --probe
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
| Ceiba scraping | not implemented; the upstream positional table parser is unverified |

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
pyproject.toml                        makes `ntu-cool` installable
tests/test_ntu_fetch.py               52 offline tests, no network
ACKNOWLEDGEMENTS.md                   what came from the upstream project
references/upstream-findings.md       why the 2019 crawler was not adopted as-is
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