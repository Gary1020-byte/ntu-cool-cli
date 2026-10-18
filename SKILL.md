---
name: ntu-course-announcements
description: Fetch NTU Cool/Ceiba course announcements.
version: 1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ntu, course, announcements, homework, exam-prep]
    related_skills: [third-party-repo-adoption, scheduled-digest-pipeline, account-provisioning-and-credentials]
---

# NTU course announcements (NTU Cool + Ceiba)

## When to Use

Load this skill when the user needs homework scope, deadlines, TA announcements, or exam scope
from NTU COOL or Ceiba. Triggers: 「hw 範圍」「考古題範圍」「助教公告」「Cool 上有什麼」,
or any request that needs what a course announced rather than what he already has.

Not for: NTU account setup, or general web fetching.

Fetches what a course *announced* **and the files it published** — handouts,
worksheets, homework sets, solutions, syllabus PDFs. The standing uses are answering
「hw 範圍是什麼、什麼時候繳交」 and 「範圍那份檔案在哪」, both of which stay unanswered
until someone reads the course.

## Verification status — read before trusting this skill

Built from a source-reading pass over `brianbbsu/NTU-Announcement-Crawler`, then
exercised against the live site with a real login. Eight distinct claims.
Do not merge them.

| claim | status |
|---|---|
| NTU Cool endpoints still exist | **verified** — `/api/v1/courses` → HTTP 401 + `{"status":"unauthenticated"}`; `/login/saml` → HTTP 200 |
| the SAML login sequence is still correct | **verified** — login succeeds, course roster and Files both fetch |
| `/api/v1/courses` lists your CURRENT courses | **FALSE — it does not.** See below. This is the biggest trap in this skill. |
| `json.loads(r.text[9:])` slice | **verified suspect** — our parser handles prefixes correctly |
| Ceiba reachable from this host | **NO** — connection timeout, see below |
| Ceiba table-parsing paths | **UNVERIFIED AND UNREACHABLE** — moot until reachability is restored |
| course FILES (handouts, worksheets, solutions) | **verified** — `fetch_course_files()`, 110 files / 114 MB across the current term |
| announcement attachments | **verified** — 5 more, separate from the Files tree |

Verified against the live site: the API returned 10 courses whose newest announcement
was three months stale, omitted three current-term courses including one of them
the author's core maths course,
and included three dead ones as `{"id": <id>, "access_restricted_by_date": true}` with
`name: null`. `fetch_courses()` therefore parses the home page instead, which yields
exactly the current roster:

```
APIsaid    <id> <current course>   <id> <current course>
           <id> <current course>   <id> <current course>
           <id> <current course>   <id> <current course>
           <id> <non-term course>          (term=null)
           + 3 rows {name: null, access_restricted_by_date: true}

Homepage   the same 7 courses, term "<term>"  ← correct
API        the 3 dead rows, and zero of the current ones
```

Course names and ids are elided: they are one account's term, and yours will
differ. That difference *is* the trap — never assume the two lists agree.

The 401 is a *good* sign: the endpoint exists and gates properly. It proves nothing about
the authenticated response shape.

## `/api/v1/courses` is NOT your current course list

**This endpoint returns courses you have EVER been associated with, and it hides the
current term's courses.** Verified by authenticated fetch: it returned 10 courses, of
which **zero** were the current term's — it listed last term's engineering
courses, a drawing course, two general-education electives, plus three rows with
`name: null`, and only one course that happened to be current.

The current-term courses are in the **homepage HTML**, not the API:

```python
r = session.get("https://cool.ntu.edu.tw/", timeout=25)
# course objects are embedded as JSON in the served page
ids = re.findall(r'"longName":"([^"]+)".*?"href":"/courses/(\d+)".*?"term":("[^"]*"|null)', r.text)
```

`"term"` carries the academic term (`<term>`), which is the field that makes
current-term filtering reliable rather than date-guessing. Courses with
`"term": null` are non-term entries (extracurricular or non-credit courses).

`access_restricted_by_date: true` on a course row means the course has ended and its
announcements return 403. That is a normal state, not an error — skip the course and
continue rather than aborting the batch. One course failing mid-batch must not abort the
rest; the per-course loop catches and continues.

`fetch_courses()` implements the homepage parse; `fetch_all_courses_historical()` still
calls the API for reading a previous term's exam schedule. **`--all-courses` uses the
homepage parse**, so it is correct and returns the current-term roster; its stderr lines
name each course plus its announcement count, which is the fastest way to spot a course
whose announcements you already have locally. To enumerate a single course, pass
`--course <id>` from the roster above rather than trusting a name match against the
historical list.

Two guards on the parse, both learned from it failing: it raises rather than returning
an empty list when the regex finds nothing (the embedded-JSON shape can change, and an
empty roster would silently mean 「no courses」), and the historical API is explicitly
**not** a fallback on empty — that is the exact wrong answer the trap produced.

### Ceiba does not respond from this machine

`ceiba.ntu.edu.tw` resolves (140.112.161.178) but every connection times out — HTTPS and
HTTP alike, connect phase, no bytes. Control test the same minute:

```
www.ntu.edu.tw    HTTP 200  0.048s
cool.ntu.edu.tw   HTTP 302  0.033s
adfs.ntu.edu.tw   HTTP 200  0.137s
ceiba.ntu.edu.tw  timeout (15s and 20s)
```

DNS resolves and sibling NTU hosts answer instantly, so this is **not** a network path or
DNS problem and **not** an NTU-wide outage. Something blocks that one host from this
server — a firewall or ACL, most likely on NTU's side, possibly by campus-network source
range.

Consequence: **only the NTU Cool path is usable here.** Ceiba scraping requires being on a
network that can reach it, or finding the host that blocks this one. Do not report Ceiba as
"crawling failed" without saying which — they are different problems with different fixes.

## The `[9:]` trap

The upstream repo does `json.loads(r.text[9:])` on every Cool response. That is the author
guessing at a prefix, not a spec — nothing in JSON or in NTU's API documents a 9-byte
prefix. Against the 401 body the slice produces `:"unauthenticated","errors":[{` and
`JSONDecodeError`.

`ntu_fetch.py` does **not** reproduce this. It locates the first `{` or `[` and parses from
there, correct whether or not a prefix exists. If a prefix ever does appear the robust
parser still works; if it disappears the hardcoded slice silently breaks.

## Dependencies

`requests` only. HTML parsing uses `html.parser` from the stdlib.

An earlier version required `beautifulsoup4` and only ever ran under Hermes'
interpreter, which ships it. The system `python3` does not, so running the script
from a shell produced `ModuleNotFoundError: No module named 'bs4'` inside the
login function. Removing the dependency fixed the whole class of problem;
`references/testing-and-interpreters.md` has the detail.

## Credentials — the hard blocker

Both platforms need NTU account + password. **This skill never stores, requests, or echoes
a password.**

- `ntu_fetch.py` reads `NTU_USER` / `NTU_PASS` from the environment, or a JSON file whose
  path is passed with `--cred-file`.
- **The user fills those in themselves, in their own shell.** Never ask for a credential as a matter
  of course, and **refuse it even if he volunteers it.** A password pasted into chat is
  durable: it lands in session history, in the Hindsight index, and in gateway logs.
  Deleting the message afterwards cleans up none of it. Route him to `read -r -s -p` in
  his own terminal, or to a `umask 077` credential file at mode 600.
- **Environment variables set in his terminal are NOT visible to you.** His shell and a
  `terminal()` call here are separate processes. When he says "我已經密碼給好了" or the
  credential seems to be missing, look for a credential FILE first, then admit you have
  nothing, rather than guessing that he failed to enter it.
- The upstream `config.yaml` approach (plaintext `ntu_pass:`) is what this skill replaces.
- Do not commit a credential file. If one is created inside a git repo, check `.gitignore`
  covers it before it is ever staged.

## Workflow

**1. Check what is already on disk before fetching anything.**

```bash
find ~/captures -iname '*hw*' -o -iname '*cool*' | head
ls ~/.hermes/attachments/
```

A previous session may already have captured it. Fetching again wastes a login round-trip
and the NTU login can rate-limit. This check matters most before a files download, where
the same course material routinely exists in both places.

**2. Dry run first — never a credentialed call before an unauthenticated one.**

```bash
python3 scripts/ntu_fetch.py --probe
```
Probes both platforms unauthenticated and prints status codes. **Known baseline on this
host: Cool 401 + 200, Ceiba UNREACHABLE — exit 0.** The Ceiba timeout is expected and
deliberately does not fail the probe; a Cool 404 would be the real signal that the upstream
moved. In that case stop and report instead of debugging auth.

**3. Fetch, writing to a capture directory.**

```bash
python3 scripts/ntu_fetch.py --all-courses \
    --cred-file ~/.ntu-creds.json \
    --since 2026-09-01 \
    --out ~/captures/
```

`--cred-file` is the working path, not env vars: an env var exported in the user's own
terminal is invisible to this process, so the script can only be driven unattended
through a file it refuses to read unless it is mode 600. `--all-courses` walks the
current-term roster and prints a per-course count to stderr, so check that output
before reading the file — a course showing `0 announcement(s) in range` is a real
finding (the course exists, it just has no announcements this term), not a fetch bug.

`--since` filters on `posted_at`, not on the term field. A course with `term: null`
still returns whatever it has. Output is a dated markdown file, one section per
announcement, raw-first per the the notes folder convention. Then summarise into `summaries/`
and update `index.md` + `log.md`.

**4. List the course FILES before anything else that touches content.**

```bash
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
```

Do this whenever the question is about *what the course published*, not merely what it
announced. Announcements carry deadlines and prose; the Files tree carries the material
those deadlines point at. See § Course FILES for why the announcement sweep alone looks
complete and is not.

**5. Report only what the source actually says.** If the worksheet lists hw4 chapters,
those are the chapters. Do not infer scope from lecture-slide order or a previous term's
exam — that inference is what produced the unverified range guess that became an
unrequested task.

When a file is needed rather than merely listed, download it to a staging directory and
let the user decide what to keep.

## Course FILES are not in the announcement body — go to the Files tree

The single biggest trap in this skill. An announcement saying 「附件」 or a body that is
literally the word "attached" is **not** a missing-attachment case to report; it is the
normal shape, and the files are fully retrievable.

Measured on the current term: **20 announcement bodies carried 6,658 characters and zero
file links, while the course Files tree held 110 files / 114 MB.** Reporting 「this course
has no attachments」 off the announcement sweep alone reads as complete and misses the
worksheets, the homework sets, the solutions, and the quiz scope documents.

Three sources, all separate stores — fetch what you need, don't conflate:

| source | function | what it holds |
|---|---|---|
| course Files tree | `fetch_course_files(s, course_id)` | handouts, worksheets, homework, solutions — the bulk |
| announcement attachments | `fetch_announcement_attachments(s, topics)` | files bound to one announcement, already carrying a signed `url` |
| announcement body | `strip_html(a["message"])` | prose only |

### Endpoint shape — read the URLs off the objects, never compose them

```
GET /api/v1/courses/{id}/folders    → folder objects (course root + subfolders)
folder["files_url"]                 → files directly in that folder
folder["folders_url"]               → child folders; recurse
```

Six plausible spellings all fail: `/api/v1/courses/{id}/files`,
`/api/v1/folders/{id}/subfolders`, `/api/v1/folders/{id}/files`,
`context_files`, `folder_files`, and `courses/{id}/content_files` return 404/400. The
folder objects carry their own URLs, so **read the fields instead of guessing the path** —
that is the whole trick. `/api/v1/courses/{id}/files` in particular looks obviously right
and is dead.

Files are grouped in meaningful folders — `course files/homework/hw4`,
`course files/lectures/20261007` — which is how you tell a homework set from a lecture
handout without reading either.

### Downloads: verify the bytes, not the status

Cool answers an expired or unauthorised signed URL with **HTTP 200 carrying the login
page**. Status alone proves nothing. `download_file()` sniffs for `<!DOCTYPE html` in the
first bytes and checks the magic prefix (`%PDF-`) against the declared content type.
A download that reports `OK` has been through both.

Each file dict's `url` is a **signed, credential-bearing link**. Never log it, never put
it in a report, never commit it.

**Filename shape:** use `display_name` (returned as `name`), not `filename` —
`filename` is the storage name and reads `1789962952_790__lecture_ch1.pdf`. Two files
named identically inside one folder get a `_2`, `_3` suffix rather than overwriting.

**Dedupe by file `id` before you count anything.** `/courses/{id}/folders` returns the
course root *and* its subfolders in one list, so a recursive walk visits `unfiled` twice
and every file inside it twice. Measured 2026-10-18: the naive walk reported **110 files
for <term>; the truth is 64.** Any diff against local copies built on the uncorrected
count is wrong in both directions — it invents duplicates that do not exist and hides
the ones that do.

### Some of these files have no text layer

Course worksheets and professor notes are frequently scanned or vector-drawn images:
a 5-page quiz-scope worksheet extracted **0 characters** from its text layer. Text
extraction reporting nothing means the layer is empty, **not** that the content is
absent — render to PNG at ~140 dpi and read the image. Never file such a PDF as
unusable on the strength of one extraction path.

### Verify the list before downloading 114 MB

```bash
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
python3 scripts/ntu_fetch.py --download-files --course <COURSE> \\
    --cred-file ~/.ntu-creds.json --files-out ~/downloads --max-mb 20
```

`--max-mb` skips oversized files. Write to a scratch or staging directory and let the user
decide what to keep — per § Filing the result, downloading straight into a working collection of notes is not
a unilateral call.

**Check what is already local before pulling anything.** `~/.hermes/attachments/` and the
existing notes often already hold the same lecture notes and homework sets that
Cool carries. Diff the manifest's filenames against local files first; the useful output
of a sweep is the list of files Cool has that you do **not**.

## Filing the result — announcements become inbox tasks, never the active list

Fetched announcements contain deadlines, and it is tempting to convert each one into a
task. **Do not.** Under the rule in `personal-os` § HARD RULE (2026-10-18), a task the
agent inferred from a source it read — a deadline in an announcement, a 「hard blocker」
— goes to `an inbox folder` with `reviewed_by_human: false`, a `推論依據` and a
`要審核的問題`. Only work the user named or approved goes to the active list.

The split that makes this cheap:

| destination | what lands there |
|---|---|
| `captures/ntu-cool-<slug>-<date>.md` | the announcement text — one file per course, all of it, unfiltered |
| `a capture folder inside the notes system` | the same file again, because a deadline in it is an action item and must be readable from the notes that holds tasks |
| `an inbox folder` | one task per inferred deadline, awaiting his ruling |

The duplicated raw file is deliberate, not a mistake: the notes folder is the study record,
the task system is the action record, and a source that matters to both belongs to both.

Two facts to carry into the report rather than into a task body as settled:

**a course with zero announcements this term may still have all its material**, in the
Files tree and on disk already — check `the summaries folder` and
`~/.hermes/attachments/` before treating a missing announcement as a gap. A task whose
stated premise is 「unknown」 when the answer was already on disk is worse than no task.

**a deadline in an announcement is not automatically an action item.** Same reasoning,
different source: an announcement states a date, the decision to act on it is his. That
is what `inbox/` is for.

Do not run the upstream Flask daemon. It is a second always-on service for a one-endpoint
need, and it pulls in an ORM the pinned versions cannot support on this interpreter.

## Reference

- `references/upstream-findings.md` — the dependency-breakage chain (Flask 1.0.2 → Jinja2 3.x,
  SQLAlchemy 1.3.8 → `sqlite3.dbapi2.version_info`), the credential shape, and the exact
  verified/unverified boundary from the adoption evaluation.
- `references/ceiba-unreachable.md` — why Ceiba is not implemented: connect timeout with
  a passing control test, and what that rules in and out.
- `references/testing-and-interpreters.md` — **read before changing the script.** Test with
  the same interpreter the user will type; `requests` is the only third-party import and
  that is deliberate; the stdlib swap caught a real first-form-vs-trap-form bug.

## Pitfalls

- ❌ Don't report 「no attachments」 from an announcement sweep. The body never carries
  the file list; the Files tree does. On the current term that is the difference between
  0 files and 110.
- ❌ Don't compose API paths for the Files tree. `/api/v1/courses/{id}/files` is the
  obvious guess and it 404s. Read `files_url` / `folders_url` off the folder objects.
- ❌ Don't trust a download's status code. An expired signed URL returns 200 with the
  login page; check magic bytes.
- ❌ Don't file an image-only PDF as unusable because extraction returned nothing. Render
  it and read the image — that is how a 0-character quiz-scope worksheet becomes a
  readable problem statement.
- ❌ Don't put a file's signed `url` in a report, a log, or a commit. It authenticates.
- ❌ Don't download straight into a working notes collection. Stage it, list it, and let the filing decision
  stay his.