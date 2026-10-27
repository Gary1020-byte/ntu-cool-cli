---
name: ntu-cool-cli
description: "Use when fetching NTU Cool/Ceiba course data: announcements, files, handouts, submission status."
version: 4
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ntu, cool, ceiba, cli, announcements, course-files, homework, handout, exam-scope, submission-status, read-only]
    related_skills: [third-party-repo-adoption, scheduled-digest-pipeline, account-provisioning-and-credentials, exam-prep-coaching]
---

# NTU Cool CLI — announcements, files, handouts, submissions

Read-only command-line access to NTU Cool (and Ceiba): what a course announced,
which files it published, where a handout actually lives, and whether a
submission was accepted.

## When to Use

Load this skill when the user needs anything NTU Cool or Ceiba holds for a
course. Triggers: 「hw 範圍」「考古題範圍」「助教公告」「Cool 上有什麼」
「講義在哪」「範圍那份檔案在哪」「繳交了嗎」「作業交了沒」「期中考範圍」
「那個 handout 哪裡下載」「Cool 上有沒有這堂課的檔案」.

Not for: NTU account setup, or general web fetching.

**What it can reach** — four different stores, one CLI:

| need | where it lives |
|---|---|
| what a course announced | `discussion_topics` (announcements + their attachments) |
| course files — handouts, worksheets, solutions, syllabus | the Files tree (`folders`) |
| a CA handout, when the Files tree is empty | the **assignment description** (`assignments`) — see § Computer Assignment handouts |
| lectures grouped by week | **modules** (`modules` → `modules/{id}/items`) |
| whether a submission was accepted | `/submissions/self` |

The standing uses are answering 「hw 範圍是什麼、什麼時候繳交」 and 「範圍那份
檔案在哪」, both of which stay unanswered until someone reads the course.

**Read-only, always.** It logs in to read and never writes, posts, or comments
on cool.ntu.edu.tw. Uploading a submission is the user's own action in the
browser — the tool will tell them what is due and where the file is, and stop
there.

## Verification status — read before trusting this skill

Exercised against the live site with a real login. Eight distinct claims.
Do not merge them.

| claim | status |
|---|---|
| NTU Cool endpoints still exist | **verified** — `/api/v1/courses` → HTTP 401 + `{"status":"unauthenticated"}`; `/login/saml` → HTTP 200 |
| the SAML login sequence is still correct | **verified** — login succeeds, course roster and Files both fetch |
| `/api/v1/courses` lists your CURRENT courses | **FALSE — it does not.** See below. This is the biggest trap in this skill. |
| `json.loads(r.text[9:])` slice | **verified suspect** — our parser handles prefixes correctly |
| Ceiba reachable from this host | **NO** — connection timeout, see below |
| requests' default UA is refused by NTU | **verified** — `python-requests` in the UA → TCP reset; `curl`/`Python-urllib`/`Mozilla` → 200. See below |
| CA handouts are reachable | **verified** — DS CA2/CA3 found in assignment-description HTML, not the Files tree; see below |
| Ceiba table-parsing paths | **UNVERIFIED AND UNREACHABLE** — moot until reachability is restored |
| course FILES (handouts, worksheets, solutions) | **verified** — `fetch_course_files()`, 91 files across the current term, 96 with announcement attachments |
| announcement attachments | **verified** — 5 more, separate from the Files tree |
| every list endpoint is paginated at 10 | **verified** — this silently loses files; see § Pagination |

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

**The CLI never touches it.** `fetch_courses()` parses the home page instead,
so every course the tool lists is current-term. `fetch_all_courses_historical()`
exists but is not reachable from any flag — measured 2026-10-23 on a real
account it answered with 10 courses against a current roster of 7, the extras
being last term's (a term-bracket course title, a placement self-test, and two
engineering courses) plus three entries with `name: null` and
`access_restricted_by_date: true`. **Every one of them had `term: null`**, so
there is no term field to filter on afterwards.

If you call that function yourself, filter by term and label the output as
historical.

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

`"term"` carries the academic term (e.g. `<term>`), which is the field that makes
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

A fixed-offset `json.loads(r.text[9:])` on every Cool response is a common shape. That is the author
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
- A `config.yaml` approach (plaintext `ntu_pass:`) is what this skill replaces.
- Do not commit a credential file. If one is created inside a git repo, check `.gitignore`
  covers it before it is ever staged.

## What this tool does — and where it stops

`ntu-cool-cli` **reads** NTU Cool. That is the whole job.

| it does | it does not |
|---|---|
| logs in and fetches announcements | file a note anywhere |
| lists the Files tree, assignments, pages, modules, handouts | create a task, or touch a notes system |
| reports `due_at`, `lock_at` and your `workflow_state` | decide what you should do about a deadline |
| downloads files into a directory you name | keep them, or file them into a collection |
| reports what the course actually said | infer a scope the course never stated |

It writes exactly one thing: a dated markdown capture of the announcements you
asked for, into the directory you named with `--out`. Everything else is stdout.

If you want to know what to do with that capture — where to file it, whether a
deadline becomes a task, how to keep one fact from drifting across many pages —
that is a note-taking system's job, not this tool's. It is a separate concern
with a separate process, and nothing in the CLI depends on it.


## Workflow

Installed as a command it is `ntu-cool-cli`; uninstalled it is
`python3 scripts/ntu_fetch.py`. Same tool, same flags, interchangeable. The
package is on PyPI: `pipx install ntu-cool-cli` (or `uv tool install
ntu-cool-cli`). To install the unreleased tip from Git instead:
`uv tool install 'git+https://github.com/Gary1020-byte/ntu-cool-cli.git'`.
The
offline tests gate is `python3 -m unittest discover -s tests` and it needs no
credentials — run it before trusting any change.

**1. Check what is already on disk before fetching anything.**

```bash
find ~/captures -iname '*hw*' -o -iname '*cool*' | head
ls ~/downloads/
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
deliberately does not fail the probe; a Cool 404 would be the real signal that the platform
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
announcement, raw-first. Then summarise it into your own notes.

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
file links, while the course Files tree held 91 files.** Reporting 「this course
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
`filename` is the storage name and reads like `<TIMESTAMP>_<ID>__<ORIGINAL-NAME>`.
Two files named identically inside one folder get a `_2`, `_3` suffix rather than
overwriting.

**Enter through the root, and paginate.** Three separate things go wrong if you do not:

`/courses/{id}/folders` returns a **flat list** of folders at every depth, not a tree.
Iterating it *and* recursing `folders_url` visits each non-root folder twice — three
times when its parent is listed too. Measured 2026-10-18: the naive walk reported
**110 files where 91 are real**.

Every list endpoint is **paginated at 10 by default**. This one actually loses data: a
folder holding 29 files answers 10, with no error and no empty-looking tail. Across a
term that was **27 of 91 files silently missing**. Follow `Link: rel="next"` — do not
raise `per_page` and assume it took, because the API caps that parameter.

`fetch_course_files()` therefore enters at `/folders/root` (falling back to the
parentless entries of `/folders`, since `/folders/root` answers **403** on at least one
non-credit course), follows `Link` in both directions, and dedupes by file `id` as a
last resort. Tests fail if any of the three is removed.

### Some of these files have no text layer

Course worksheets and professor notes are frequently scanned or vector-drawn images:
a 5-page quiz-scope worksheet extracted **0 characters** from its text layer. Text
extraction reporting nothing means the layer is empty, **not** that the content is
absent — render to PNG at ~140 dpi and read the image. Never file such a PDF as
unusable on the strength of one extraction path.

### Pagination is the trap that silently loses files

Canvas defaults to `per_page=10` and caps the parameter. A folder holding 29 files
answers 10 — **no error, no empty-looking tail**. Across one term that was 27 of 91 files
missing.

Follow `Link: <...>; rel="next"` from the response headers. Do not "fix" it with a bigger
`per_page` and assume it took; the Link header is the only pagination contract the API
honours. `_paged_get()` in `scripts/ntu_fetch.py` does this.

**A verification that runs the same code on both sides proves only symmetry.** A
dedupe check comparing two runs of one implementation reported 64 = 64 and passed while
both sides were still truncating at 10. Assert the two independent properties separately:
no duplicates *and* nothing missing (raise `per_page`, or compare against a second entry
point such as the parentless-list fallback).

Files are grouped in meaningful folders — `course files/homework/hw4`,
`course files/lectures/20261007` — which is how you tell a homework set from a lecture
handout without reading either.

### Verify the list before downloading the whole term

```bash
python3 scripts/ntu_fetch.py --list-files --course <COURSE> --cred-file ~/.ntu-creds.json
python3 scripts/ntu_fetch.py --download-files --course <COURSE> \
    --cred-file ~/.ntu-creds.json --files-out ~/downloads --max-mb 20
```

`--max-mb` skips oversized files. Write to a scratch or staging directory and let the user
decide what to keep — downloading straight into a working collection of notes
is not a unilateral call.

**Check what is already local before pulling anything.** Your downloads folder and your
existing notes often already hold the same lecture notes and homework sets that
Cool carries. Diff the manifest's filenames against local files first; the useful output
of a sweep is the list of files Cool has that you do **not**.

## The `python-requests` User-Agent gets the connection reset

**This is the single most expensive failure in this skill, and it looks like a
network fault.** Measured 2026-10-21 on this host, same URL, same TLS stack,
minutes apart:

| User-Agent | result |
|---|---|
| `curl/8.18.0` | HTTP 200, 10847 bytes |
| `Python-urllib/3.12` | HTTP 200 |
| `Mozilla/5.0` | HTTP 200 |
| `python` | HTTP 200 |
| *(empty)* | HTTP 200 |
| `python-requests/2.32.5` | **ConnectionResetError(104)** |
| `curl/8.18.0 python-requests` | **ConnectionResetError(104)** |

The filter matches the token `python-requests` **anywhere** in the header, so
prefixing a browser UA onto the default does not help. The failure is a TCP
reset during the request, not an HTTP status — which is why it reads as "the
host is down" rather than "we are being filtered".

Diagnostic that separates the two in one command:

```bash
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 https://cool.ntu.edu.tw/login/saml   # 302
python3 -c "import requests; requests.get('https://cool.ntu.edu.tw/login/saml', timeout=20)"  # reset
```

Same minute, same host, different client — that is a UA filter, not an outage.

**Fix: set the User-Agent on the session, not per request.** Every hop of the
SAML chain (cool, ADFS, the API base) goes through one session, so the header
must be set in `_session()`. `USER_AGENT` was already defined at the top of the
script and never applied — that was the bug.

Retrying cannot fix this. 8 consecutive login attempts with the default UA all
failed while curl and stdlib `urllib` both succeeded in the same minute.

## Exam scope lives in the worksheet pairing, not the syllabus

Some courses state the exam rule in an announcement, and the rule is usually that the exam **is**
the homework:

> 我們會在上課前先丟上去一次一單元的空白習題… 然後**小考內容就是習題**。

That converts a scope question into a file-location question. The blank worksheet posted before
that class is the exam; the `詳解` uploaded after the TA session is the answer key for the *same
numbered problems*. Fetch the pair together — one list call each — and you have both the scope and
the expected working, before reading anything.

```bash
python3 scripts/ntu_fetch.py --list-files --course a course --cred-file ~/.ntu-creds.json
```

**When an announcement says the quiz is the homework, fetch the pair.** The rule
generalises: if the announcement says 「小考內容就是習題」 (or any equivalent), then
look for **both** the blank worksheet and the solution key with the same numbering,
and treat the optional-practice file as explicitly not graded. So the search is:

```
<COURSE>_ch<N>_習題.pdf       ← the scope (blank, posted before class)
<COURSE>_ch<N>-2_習題詳解.pdf  ← the key for the same numbering
<COURSE>_ch<N>_自主練習.pdf    ← 自主練習 is explicitly NOT graded
```

Read the output by **chapter + file role**, not by name similarity. The role is what
distinguishes the scope from the key from the ungraded extra — the names only vary
by course.

**A frequency quiz covers one class period, not the textbook chapter.** A 「第二次小考」 on the
second week of loading is a fraction of the chapter; planning to the chapter boundary costs
hours on material nobody is graded on. The announcement's own word for the scope outranks
the syllabus's chapter range.
**The givens are often designed to pair up.** A distributed load whose total resolves to the point
load printed beside it (`q × 1.2 m = 22 kN = P`) is the author confirming your reading. Record
that beside the transcription so a later session does not see a suspicious digit and 「correct」 it
— see `exam-prep-coaching` § Record surprising given values as verbatim.

### Scope the announcement sweep to one course

`--all-courses` returns every current course's announcements, so a per-course grep over its output
matches other courses' material — a 「10/14 期中考」 line found this way may belong to Fluid
Mechanics, not the course being taught. Re-run with `--course <name>` when the answer is about one
course:

```bash
python3 scripts/ntu_fetch.py --cred-file ~/.ntu-creds.json \
    --course <course-name> --since 2026-06-01 --stdout 2>/dev/null | grep -A3 '^## '
```

Cheap, and it is the difference between the right exam date and a neighbour's.

### Prove absence across the whole roster before reporting a date is missing

A per-course sweep tells you what that course announced. It cannot tell you the
course never announced something — only that you looked in one place. Run the
whole roster, then attribute:

```bash
# 1. does ANY current course publish an exam date?
python3 scripts/ntu_fetch.py --cred-file ~/.ntu-creds.json --list-files \
    --all-courses 2>/dev/null
for c in a course a course a course一; do
  echo "═══ $c ═══"
  python3 scripts/ntu_fetch.py --cred-file ~/.ntu-creds.json --course "$c" \
      --since 2026-06-01 --stdout 2>/dev/null \
    | grep -iE '期末|期中考|考試時間|考試日期|範圍'
done
```

The attribution is the deliverable. A course whose own sweep is empty while a
sibling's sweep carries `10/14 10:20-11:50 第一次期中考` establishes a real,
reportable finding: **Cool publishes this course's quizzes but not its exam
date** — so the date has to come from the university's schedule system, not from
this tool. Reporting only the first half produces 「Cool 上沒有日期」, which reads
as a fetch failure rather than as the true and much narrower claim.

**Say which kind of absence it is.** Three different states, one sentence apart:

| observation | claim |
|---|---|
| course's sweep empty, siblings' sweeps populated | the tool works; this course has no such announcement |
| course's sweep empty, siblings' also empty | suspect the endpoint moved — check `--probe` before believing it |
| date present but only for a different course | attribute it, don't report it as his |

A course that has already sat an exam still shows the announcement afterwards, so
a past exam's date is normally still findable — which makes an empty result for a
*finished* exam suspicious rather than expected, and worth saying so.

### The course's own pages answer 「我交了嗎」 and 「還來得及嗎」 faster than any sweep

`/assignments` tells you *what* is assigned. To answer *his* question — 「今天有作業嗎」
and 「我繳了嗎」 — the fastest path is the roster sweep, not a per-course guess:

```python
# one pass over every current course's assignments, filtered to the days around today
for c in nf.fetch_courses(s):
    for a in paged(f"{nf.API}/courses/{c['id']}/assignments?per_page=100"):
        due = a.get("due_at")
        if due and dt.date() in (today - 1, today, today + 1):
            sub = get(f"{nf.API}/courses/{c['id']}/assignments/{a['id']}/submissions/self")
            print(c["longName"], a["name"], dt, sub.workflow_state)
```

This answers in one pass: which course has something due today, whether he turned it
in, and what else is due tomorrow. Run it whenever the question is 「今天有什麼交」 rather
than one course's scope — a per-course sweep answers a question he did not ask.

### 「今天」must be read from a clock, not from the session header

The date in a session's context can be a day stale, and every deadline you report is
computed against it. Two independent clocks, and the remote one settles it:

```bash
TZ=Asia/Taipei date '+%Y-%m-%d %H:%M %A'          # host clock, labelled
# and, from the same request, the server's own clock:
r.headers.get("Date")                                 # e.g. Fri, 23 Oct 2026 10:44:04 GMT
```

Compare the two. When they agree, the date is established; when the session's stated
date differs from both, the session's date is wrong and every 「T-2 hours until the
deadline」 you computed from it is wrong by a day — which silently turns 「plenty of
time」 into 「already closed」 or the reverse.

**Cross-check the remote clock before reporting any remaining-hours figure**, and
prefer the remote one: it is the clock the course's own system runs on, so it is what
the deadline is measured against.

**Report the missed ones in the same breath.** The sweep almost always surfaces
something he has not done — on a course, the answer to 「今天有作業嗎」 turned out to be
「有,而且上一份也沒交,補交視窗已經關了」. The second fact is the one that costs him
points, and it is invisible if you report only today's deadline.

## The four stores, and which one holds what

| store | endpoint | holds |
|---|---|---|
| assignment description | `/assignments` → `data-api-endpoint` | CA handouts, homework sets |
| modules | `/modules` → `/modules/{id}/items` | lectures, week-grouped |
| Files tree | `/folders` → `files_url` | course files (can be nearly empty) |
| announcement attachments | `/discussion_topics` → `attachments[]` | files bound to one announcement |

**Which store you read decides whether you find the material.** A course whose
entire handout set is three assignment descriptions looks empty in Files — the
Files tree held one file while the other two were absent from it, from the
announcement attachments, and from every module. Read them in the order above;
a sweep of one store is not a sweep of the course.

Each store has its own trap, and the traps are recorded in three references:

| reference | read it when |
|---|---|
| `references/reading-course-state.md` | 「我交了嗎」「有什麼要交」「期限是什麼」 — submissions, course pages, the calendar page, and how to read a deadline |
| `references/exam-scopes-and-course-material.md` | 「範圍是什麼」「那份檔案在哪」「我的位置是哪」 — the Files tree's lock states, attachments, seating charts, encrypted PDFs, and telling one course's file from another's |
| `references/homework-and-due-dates.md` | 「作業啥時交」「有沒有漏的」「我交了沒」 — the homework roster, what a syllabus plans but never assigns, paper hand-in versus upload, and the shape of a complete answer |

### Computer Assignment handouts live in the assignment description

**CLI flags: `--list-handouts` (the links) and `--download-handout` (the bytes).**

**The Files tree is not where CA material is.** A course whose entire handout
set is three assignment descriptions looks empty in Files. Measured on one
course: the Files tree held exactly **one** file, while the other two were
absent from it, from the announcement attachments (0), and from every module.

They are in the **assignment description HTML**:

```
GET /api/v1/courses/{id}/assignments
  → [<ASSIGNMENT_ID>] 'CA1' desc contains a link to file id <FILE_ID>
  → [<ASSIGNMENT_ID>] 'CA2' desc contains a link to file id <FILE_ID>
  → [<ASSIGNMENT_ID>] 'CA3' desc contains a link to file id <FILE_ID>
```

The description is HTML, and the file id sits in a `data-api-endpoint`
attribute:

```html
<a class="instructure_file_link" title="連結"
   href="https://cool.ntu.edu.tw/courses/<COURSE_ID>/files/<FILE_ID>/download"
   data-api-endpoint="https://cool.ntu.edu.tw/api/v1/courses/<COURSE_ID>/files/<FILE_ID>"
   data-api-returntype="File"><PREFIX>_CA3.zip</a>
```

`find_attachments()` does **not** find this — it greps for `href="....pdf|docx|zip"`,
and this href ends in `/download`, not in a file extension.

Getting the bytes is a **two-hop** process, and the first hop looks like a
failure if you are not expecting it:

1. `GET` the `data-api-endpoint` → returns **JSON describing the file**, not the
   file. `content-type: application/json`, body starts `{"id":<FILE_ID>,...}`.
   A naive `download_file()` against this URL fails the `%PDF-` magic check with
   a misleading "magic mismatch".
2. The JSON carries a **signed `url`**. `GET` that → the real bytes.

Modules are the other store, and they resolve the same two-hop way:
`GET /modules/{id}/items` → a `File` item's `url` is an API link → JSON →
signed `url` → bytes.

## This repo's own layout — where to change what

The repo is **two layers bound together**, and most of its bulk is documentation,
not code. Say this before anything else when someone asks 「架構是什麼」:

| layer | file | what it is |
|---|---|---|
| the tool | `scripts/ntu_fetch.py` (~1090 lines) | the only executable code |
| the manual | `SKILL.md` (large) | the agent-facing playbook: workflows + every trap this tool hit |
| the depth | `references/*.md` | same material, one file per topic |
| the packaging | `pyproject.toml` + `.github/workflows/` | `scripts/ntu_fetch.py` → PyPI `ntu-cool-cli`; CI + publish |

**What this repo is not.** It is a read-only fetcher, not a filing system.
Where a capture is filed, which deadline becomes a task, and how one fact is
kept from drifting across many pages are a separate process with its own
rules, and those rules do not belong here. The tool's boundary is stated in
§ What this tool does — and where it stops.

**`SKILL.md` being long is not bloat.** Each section is a 「I assumed A, it was B,
because C」 trap record. Do not summarise it as documentation noise and do not
propose trimming it — the length IS the asset.

**The runtime shape of `ntu_fetch.py` is five steps:**

```
_session()      → one requests.Session; the User-Agent is set HERE, once
cool_login()    → NTU ADFS login → session cookies
fetch_courses() → current-term roster (homepage parse, NOT /api/v1/courses)
fetch_xxx()     → one API endpoint each; all parallel, none depend on each other
render()        → JSON/HTML → markdown
```

**Adding a capability is two edits, not a refactor:** one `fetch_xxx()` function
plus one argparse flag in `main()`. The `fetch_*` layer is deliberately flat so
it stays that way — resist wrapping them in a base class or a registry.

| to change | edit |
|---|---|
| add a flag | `main()`'s argparse block |
| add a data source | a new `fetch_xxx()` next to its siblings |
| fix login | `cool_login()` |
| change how the agent uses the tool | `SKILL.md` |
| ship a new version | `pyproject.toml`'s `version`, then the release chain in `references/release-and-packaging.md` |

### Reading the repo from a laptop over SSH

The repo lives on the server (`~/services/ntu-cool-announcements-skill/`). To
edit it from a Windows laptop, use VS Code's Remote-SSH against the server and
`File → Open Folder` with the absolute server path; the integrated terminal is
the server's own shell, so `python3 scripts/ntu_fetch.py --probe` runs against
the real tool. Recipe and the local-vs-remote traps: `ide-acp-integration` §
Editing server-side files from a laptop IDE.

## Reference

### Read these for a course question

- `references/reading-course-state.md` — submissions, course pages, the calendar
  page, and how to read a deadline.
- `references/exam-scopes-and-course-material.md` — the Files tree's lock states,
  announcement attachments, seating charts, encrypted PDFs, and telling one
  course's file from another's.
- `references/homework-and-due-dates.md` — the homework roster, what a syllabus
  plans but never assigns, paper hand-in versus upload, and the shape of a
  complete answer.

### Read these before changing the tool

- `references/api-findings.md` — the platform's real response shapes, the pagination
  contract, the User-Agent filter, the credential shape, and which claims are
  verified against the live site versus inferred.
- `references/testing-and-interpreters.md` — **read before changing the script.** Test with
  the same interpreter the user will type; `requests` is the only third-party import and
  that is deliberate; the stdlib swap caught a real first-form-vs-trap-form bug.
- `references/release-and-packaging.md` — how the two install paths differ, why a
  wheel in `dist/` is not a release, the release checklist, and the branch→main→
  PyPI chain a fix has to travel.
- `references/computer-assignment-retrieval.md` — how to get a CA handout when the
  Files tree is empty, including the two-hop download and the signed-URL rule.
- `references/manifest-status.md` — what "did we fetch this?" can mean without a
  manifest, and why the absence of one is a deliberate trade.
- `references/seating-chart-lookup.md` — reading an exam seating chart: room
  heading per page, ID→row coordinates, the seat-number floor map + 梯次表 type,
  and the two-exams-two-charts trap.

### Read this to explain a boundary

- `references/ceiba-unreachable.md` — why Ceiba is not implemented: connect timeout with
  a passing control test, and what that rules in and out.

## Pitfalls

### Reading the course

- ❌ Don't report 「no attachments」 from an announcement sweep. The body never carries
  the file list; the Files tree does. On the current term that is the difference between
  0 files and 96 (91 in the tree, 5 bound to announcements).
- ❌ Don't treat an empty `/assignments` exam list as 「this course has no
  exam」 — the course calendar page (`/pages/ke-cheng-xing-shi-li`) carries
  exam rows that never appear as assignments.
- ❌ Don't read the 截止 column of a course calendar table as a due date; it is
  the assignment tag of that week.
- ❌ Don't answer one exam's seat from another exam's chart. A course publishes a
  chart per exam, and the paper chart (IDs in seats) and the lab chart (seat-number
  map + 梯次表) key differently.
- ❌ Don't report a lab exam's venue from the seating chart. The chart carries a
  大門 marker, not a room; the room comes from an earlier announcement — name it.

### Walking the Files tree

- ❌ Don't walk `/courses/{id}/folders` and recurse. It is a flat list at every depth,
  so every non-root folder gets counted two or three times.
- ❌ Don't assume one page is the whole list. Canvas defaults to `per_page=10` and caps
  the parameter — 27 of 91 files were missing that way, with nothing to notice.
- ❌ Don't rely on `/folders/root` alone. It 403s on a non-credit course while the list
  endpoint still answers; falling back to the parentless entries keeps the course.
- ❌ Don't compose API paths for the Files tree. `/api/v1/courses/{id}/files` is the
  obvious guess and it 404s. Read `files_url` / `folders_url` off the folder objects.

### Downloading

- ❌ Don't trust a download's status code. An expired signed URL returns 200 with the
  login page; check magic bytes.
- ❌ Don't file an image-only PDF as unusable because extraction returned nothing. Render
  it and read the image — that is how a 0-character quiz-scope worksheet becomes a
  readable problem statement.
- ❌ Don't put a file's signed `url` in a report, a log, or a commit. It authenticates.
- ❌ Don't download straight into a working notes collection. Stage it, list it, and let
  the filing decision stay his.

### Deadlines and submissions

- ❌ Don't report an `on_paper` assignment's deadline from `due_at` alone. `lock_at`
  is usually `None` for paper hand-ins, and the venue, the hand-in hours and the
  「逾時不候」 cutoff live only in the announcement — the API has no upload window
  to close. A null `lock_at` is not a missing deadline.
- ❌ Don't skip the student's own `workflow_state` when answering a due-date
  question. 「什麼時候交」 and 「我交了沒」 are one deliverable; the date alone
  reads as done.

### Using the tool

- ❌ Don't trust `load_credentials()` to return a dict — it returns a
  `(user, password)` tuple — and don't pass it a bare `~` path; the credential
  guard stats the literal string and fails. Expand `~` yourself.
- ❌ Don't claim 「新版本已上架」 because the version number or a wheel in
  `dist/` moved — those are build artifacts. Verify against the PyPI index.