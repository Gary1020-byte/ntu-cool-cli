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
| a CA handout, when the Files tree is empty | the **assignment description** (`assignments`) — see § CA handouts |
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
being last term's (`【114-1 寒假】…`, `114 微積分學前自我檢測`, `<COURSE>`,
`工程圖學`) plus three entries with `name: null` and
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

## Workflow

Installed as a command it is `ntu-cool`; uninstalled it is
`python3 scripts/ntu_fetch.py`. Same tool, same flags, interchangeable. The
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
`filename` is the storage name and reads `<TIMESTAMP>_<ID>__<ORIGINAL-NAME>.pdf`. Two files
named identically inside one folder get a `_2`, `_3` suffix rather than overwriting.

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
decide what to keep — per § Filing the result, downloading straight into a working
collection of notes is not a unilateral call.

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

Read the output by **chapter + file role**, not by name similarity:

```
<COURSE>_ch<N>_習題.pdf        ← the scope (blank, posted before class)
<COURSE>_ch<N>-2_習題詳解.pdf  ← the key for the same numbering
<COURSE>_ch<N>_自主練習.pdf    ← 自主練習 is explicitly NOT graded
```

**A frequency quiz covers one class period, not the textbook chapter.** A 「第二次小考」 on the
second week of loading is a fraction of Chapter 2; planning to the chapter boundary costs hours on
material nobody is graded on. The announcement's own word for the scope outranks the syllabus's
chapter range.

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

## Computer Assignment handouts live in the assignment description, not the Files tree

**CLI flags: `--list-handouts` (the links) and `--download-handout` (the bytes).**

**The Files tree is not where CA material is.** A course whose entire handout
set is three assignment descriptions looks empty in Files.

For a CS course (course <COURSE_ID>) the Files tree held exactly **one** file
(`<PREFIX>_CA1.pdf`) — while `<PREFIX>_CA2.zip` and `<PREFIX>_CA3.zip` were both absent from it,
from the announcement attachments (0), and from every module.

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

### The full set of stores, in the order worth checking

| store | endpoint | holds |
|---|---|---|
| assignment description | `/assignments` → `data-api-endpoint` | CA handouts, homework sets |
| modules | `/modules` → `/modules/{id}/items` | lectures, week-grouped |
| Files tree | `/folders` → `files_url` | course files (can be nearly empty) |
| announcement attachments | `/discussion_topics` → `attachments[]` | files bound to one announcement |

### Your own submission status lives at `/assignments/{id}/submissions/self`

**CLI flag: `--list-submissions`.** The endpoint below is what it calls, and
what each field means.

**This is the endpoint that answers 「我有沒有交」 and 「遲交還能不能補」.**

```
GET /api/v1/courses/{id}/assignments/{id}/submissions/self   → 200, your submission
GET /api/v1/courses/{id}/assignments/{id}/submissions?self=1 → 403 (do not use)
```

Measured 2026-10-22 on a course (<COURSE_ID>): the `?self=1` list form returned **403 Forbidden**
on every assignment, while `/submissions/self` returned 200 for all of them. Same session,
same credentials — only the path differs.

Fields that matter:

| field | meaning | how to read it |
|---|---|---|
| `workflow_state` | `unsubmitted` / `submitted` / `graded` | `unsubmitted` + `submitted_at: null` = never handed in |
| `submitted_at` | UTC ISO | convert to Taipei before comparing to `due_at` |
| `score` | grade, `null` if ungraded | `points_possible` is per-assignment (1.75% on a course) |
| `seconds_late` | seconds past due | **non-zero on an assignment that was never submitted** — it is "how long late it *would* be", not proof of a late submission |
| `late_policy_status` | `late` / `missing` / `null` | `missing` = never turned in |

**`due_at` and `lock_at` are both UTC, and `lock_at` is the real deadline.**
On a course: `due_at: 2026-10-22T15:59:59Z` (= 台北 10/22 23:59) and
`lock_at: 2026-10-23T00:00:00Z` (= 台北 10/23 08:00). The 8-hour gap is the buffer the
course page promises. **A `lock_at` in the past means the upload window is closed** — the
`seconds_late` counter keeps running forever on an unsubmitted assignment, so it is
*not* evidence you can still turn it in.

Pair this with the course's 「作業遲交政策」 page rather than assuming a 24-hour grace.

### Course pages are addressed by slug, and the slug is on the module item

**CLI flags: `--list-pages` (the slugs) and `--show-page <slug>` (the body).**

The 課程大綱 / 課程行事曆 / 遲交政策 / 繳交方式 / 撰寫原則 live in `/pages`, and the
module item carries the slug in `page_url`:

```
module item → {"type": "Page", "page_url": "ke-cheng-da-gang",
               "url": ".../api/v1/courses/<COURSE_ID>/pages/ke-cheng-da-gang"}
GET /api/v1/courses/{id}/pages/ke-cheng-da-gang   → 200, body = HTML
```

`content_id` is **absent** on Page items (it is present on File items), so
`/pages/{content_id}` → `/pages/None` → 404. Read `page_url` or the item's own `url`.

These pages carry the rules no other endpoint has: the exam date and scope, the
13-assignment schedule, the grading breakdown, the late policy, the submission-format
requirement (single PDF), and the report-writing rubric. **A course can have zero
announcements and still be fully documented here** — the 4-announcement sweep for
a course hid all of it.

### A course can have NO modules, NO pages, NO quizzes, and NO calendar

**CLI flag: `--list-modules`.**

**`/pages` reached only through `/modules` is a chain of two links, and either link can
be dead.** A course that uses neither of them has no course-outline page, no exam-date
page, and no quiz list — and every endpoint returns a shape that looks like an empty
result rather than an error.

Measured on a course (<COURSE_ID>): `/modules` → `[]`, `/pages` → **404 「該頁面在此課程已被停用」**,
`/quizzes` → **404**, `/calendar` → **404**, `/discussion_topics` → `[]`.
Only `/assignments` and the Files tree carried anything.

**A `[]` from `/modules` is not 「the course has no material」** — it means this course
publishes nothing through modules. The material can be entirely in the Files tree and in
the assignment descriptions. Read the empty result as a fact about the *store*, not about
the course.

**So the per-course endpoint map is not fixed — probe it.** One cheap loop over the
endpoints settles the shape of the course you are actually working with, and tells you
which stores to bother with:

```python
for path in ["/assignments?per_page=100", "/modules?per_page=100",
             "/pages?per_page=100", "/quizzes?per_page=100",
             "/calendar", "/discussion_topics?per_page=100",
             "/assignment_groups?per_page=100"]:
    r = s.get(f"{API}/courses/{cid}{path}", timeout=30)
    # 200 + non-empty list = this store has content
    # 200 + []            = this store is unused by this course
    # 404                = this store is disabled for this course
```

**Where the schedule comes from when the course pages are dead:** the **syllabus PDF**,
which courses publish in the Files tree and which is usually a single page carrying the
whole semester — week number, date, course outline, the assignment tag, the exam, and the
grading breakdown. That PDF is the fallback for everything `/pages` would have given you.
Read it with `pymupdf` and treat its week table as the schedule:

```
W6  10/16  Logic Minimization and Optimization (HW 2)
W7  10/23  Binary Representation and Arithmetic Circuits (Quiz 1)
W8  10/30  Midterm
```

**When the syllabus gives a week but not a clock time, say the time is unknown.** A quiz
listed as 「Quiz 1」 on a week with no published time is a genuine gap — report it as one
and route the question to the TA, rather than inferring a time from the class slot.

### A stored deadline goes stale — re-read `/assignments` before planning around any date

Canvas records **when the professor edited the assignment** in `updated_at`. A task file
or a note written days earlier is a snapshot of the deadline *as it was then*, and a
professor can move a due date without posting any announcement. The `updated_at` field is
how you detect that:

```
GET /api/v1/courses/{id}/assignments
  → {"id":424916, "name":"HW2",
     "due_at":"2026-10-30T09:30:00Z",      ← live value
     "updated_at":"2026-10-22T14:03:37Z",  ← professor edited here
     "created_at":"2026-10-17T05:35:21Z"}
```

**Rule: the live `/assignments` `due_at` wins over any date you wrote down earlier.**
When it disagrees with a task file, say so out loud, correct the file, and name
which one was wrong. A task file carrying a due date nobody re-checks is exactly the kind
of stale record that costs a whole assignment.

**Compare `updated_at` against the date you recorded.** If the assignment was edited after
your note was written, treat the deadline as suspect even when the value happens to match.

**A deadline in a note file is a claim, not a fact.** Before building a plan, a
reminder, or a countdown around any course deadline, re-read the source that owns it.

### A syllabus's week column is not a due date

Syllabus schedules pair a **date** with a **course outline**, and the assignment tag rides
along in the same row:

```
6   10/16   Logic Minimization and Optimization (HW 2)
```

This means **HW2 belongs to the 10/16 week** — it covers the unit taught that week. It does
**not** mean HW2 was due on 10/16. The due date comes from `/assignments` and nowhere
else. Reading the week column as the deadline is a one-day error that becomes a missed-week
error when the two happen to be a week apart — and the assignment is then still open when
you thought it was closed.

### A deadline value can be right while its weekday label is wrong

`due_at` is read from the API and is a fact. The **weekday you write beside it** is not —
it is a calendar fact you inferred, and inference is where this goes wrong.

The recurring mechanism: knowing today's weekday, then reasoning 「yesterday was Thursday,
so the date one week out is Thursday too」. That holds only when the gap is exactly 7 days.
A due date pushed a week out from a *different* day is not, and the error propagates
because nothing in the workflow ever recomputes it — the date was verified, so the label
beside it was trusted.

**Compute every weekday you write, with `date -d`, at the moment you write it:**

```bash
for d in 2026-10-16 2026-10-22 2026-10-23 2026-10-29 2026-10-30; do
  echo -n "$d "; date -d "$d" '+%A (週%u)'
done
```

**A weekday label is worse than no label.** It carries the authority of the verified date
sitting next to it, and it gets copied into every task file, plan page and summary that
touches the deadline — so one inference error becomes six artifacts that all read as
checked.

**Cross-check the whole schedule instead of trusting one date.** When a syllabus publishes a
week-by-week table, run its dates through `date -d` in a single loop. A course whose
fifteen class dates are *all* the same weekday tells you something no single row does:
which day homework is handed out, whether a due date lands in class, and — when a deadline
is 「上課前交給助教」 — that the hand-in is the same day as the due date rather than the day
before.

```bash
# syllabus week table → every date labelled, one pass
printf '%s\n' 9/11 9/18 10/02 10/16 10/23 10/30 | \
  while read -r m d; do echo -n "2026-$m-$d "; date -d "2026-$m-$d" '+%a'; done
```

### An empty `url` on a file means two different things

`GET /api/v1/courses/{id}/files/{id}` returns `unlock_at`, `lock_at`, `locked`,
`hidden_for_user`. A file can be **visible in the Files tree** and still be undownloadable.
Two distinct causes, and they need different answers:

| | meaning | how to tell |
|---|---|---|
| `locked: true`, `unlock_at` in the future | **not released yet** — the course will publish it later | `unlock_at` is set and in the future |
| `hidden_for_user: true` | **not published to students** — the professor hid it from the Files listing | `hidden_for_user` is true |

A homework PDF attached to an assignment description can carry `hidden_for_user: true`
while the assignment's own `description` links to it and the bytes download fine — the
flag refers to the course Files listing, not to the assignment's attachment. **Try the
download before reporting the file as unavailable**, and check `unlock_at` before
concluding the download is broken.

### A solution file can be locked until a future date

`GET /api/v1/courses/{id}/files/{file_id}` returns `unlock_at`, `lock_at`, `locked`,
`hidden_for_user`. On a course, `<HOMEWORK-N>_solutions.pdf` existed with
`unlock_at: 2026-10-23T01:00:00Z` (台北 10/23 09:00) — **the signed `url` came back empty
and the download was not possible yet**. An empty `url` on a file you can see in the
Files tree means "not released yet", not "download is broken". Check `unlock_at` before
concluding the file is missing.

**A locked course key is not a reason to wait.** The course's own solution PDF unlocks
at a future hour, but the **textbook's published solutions manual** is available now and
carries the same answers — for concept questions it carries the *prose* answer, not just
a number. When a homework set needs solving, go get the manual rather than polling for
`unlock_at`. Recipe: `course-assignment-submission/references/textbook-solutions-manual-and-verification.md`.

### A locked file's `url` field is empty — fetch the metadata, not the tree entry

The Files-tree entry and the file-metadata response are different shapes. A tree entry
may carry a `url` that is present-but-unusable, while the metadata response
(`GET /api/v1/courses/{id}/files/{id}`) carries `display_name`, `size`, `unlock_at`,
`lock_at`, `locked`, `hidden_for_user` — the fields you need to decide *why* a download
is not possible. Fetch metadata for every file you intend to download rather than
relying on what the tree listing happened to include.

### `discussion_topics` needs `only_announcements=true` or it returns `[]`

```
GET /api/v1/courses/{id}/discussion_topics                      → 200, body = []   ← WRONG
GET /api/v1/courses/{id}/discussion_topics?only_announcements=true&per_page=1000
                                                                  → 200, real list
```

Measured 2026-10-23 across all seven current courses: the bare path returned an
**empty array with HTTP 200** for every course, while the same URL with
`only_announcements=true` returned 4–6 announcements each. An empty list here is
**not** "no announcements" — it is the missing parameter. `fetch_announcements()`
in `ntu_fetch.py` already passes the right params; a hand-rolled `s.get()` that
omits them silently produces zero results and looks like a course with no news.

**This matters for exam discovery.** a course (<COURSE_ID>) has **zero assignments**
in Cool — its 期中考 exists only in an announcement + a seating-chart attachment +
the syllabus PDF. A sweep that reads `/assignments` alone reports "no exams for
this course" and is wrong. Read all three stores per course:
`/assignments` (dated work), `/discussion_topics?only_announcements=true`
(prose + attachments), and the course pages/syllabus (scope + rules).

### Announcement attachments carry the exam logistics

`/discussion_topics` items include `attachments[]` with `display_name` and `id`.
The a course 期中考 announcement (posted 5 days before the exam) carried
`期中考教室座位表.pdf` — the seating chart, which is the only place the room
split is published. Download it via the two-hop file fetch, not by guessing a path.

### A course code and a student ID differ by one letter — check which one you have

NTU ESOE course codes are six digits (`<SIX-DIGIT-CODE>` for <COURSE> / ESOE <CODE>) and appear
in the handout's own header line, so they are trivially mistaken for the student ID
(`B` + eight digits). The two are used in different places and neither is guessable:

| the value | where it belongs | where to get it |
|---|---|---|
| course code `<SIX-DIGIT-CODE>` | the handout's title line | the PDF header |
| student ID `BXXXXXXXX` | the `@ID` field, the archive filename, the seating chart | the course's **already-accepted earlier submissions** |

**Read the student ID off the accepted earlier submissions** — the submission
attachment's `display_name` is the archive the grader already took and graded, so it
carries the ID and the exact filename format the grader expects, in one field:

```
GET /api/v1/courses/{id}/assignments/{assignment_id}/submissions/self
  → attachments[].display_name = "CA1BXXXXXXXX.zip"
```

Note what that single field settles: the ID, **and** the format. The format document
said `<ARCHIVE-WITH-ID>.zip` (with an `R`); the two archives the grader had actually
accepted were `CA1BXXXXXXXX.zip` and `CA2BXXXXXXXX.zip` (no `R`). The document and the
grader disagree, and the grader wins.

### A seating chart is a lookup, not a diff — and "not found" is ambiguous

Seating charts are keyed by student ID, so a lookup with the right ID is a lookup with
the wrong key is a false 「he isn't registered」. Search the PDF's **text layer** for
the ID and read its coordinates to get the row and the room:

```python
import pymupdf
d = pymupdf.open("seating.pdf")
for i in range(d.page_count):
    words = d[i].get_text("words")
    for w in words:
        if w[4] == STUDENT_ID:
            x0, y0, x1, y1 = w[:4]
            row = [v for v in words if abs((v[1]+v[3])/2 - (y0+y1)/2) < 8]
            row.sort(key=lambda v: v[0])
            print("room heading:", d[i].get_text().split("\n")[0].strip())
            print("row:", " | ".join(v[4] for v in row))
```

The room is the heading on that page (「<ROOM> 教室座位表」 / 「<ROOM> 教室座位表」), and the
row's horizontal order gives the seat.

**A miss is ambiguous between "wrong ID" and "not on the chart"** — so before
reporting that a student is not on a chart, confirm you searched for the ID and not
for a course code. A chart of ~66 IDs with no hit for a value that is visibly a
course code is a finding about the *value*, not about the student.

### PDFs may be password-protected — render and read the image

`<SYLLABUS>.pdf` and `<CLASS-NOTES>.pdf` (both
a course) open with `is_encrypted=True`. The lab-notes password `<PASSWORD>`
(from the 9/14 announcement) authenticates the syllabus and class notes
(`d.authenticate('<PASSWORD>')` → 6 = success) but **not** the seating chart.

Unlock first, then measure each page — a partially-extractable document is the case that
misleads:

```
doc = pymupdf.open(path); doc.authenticate("<PASSWORD>")
for i in range(doc.page_count):
    print(i + 1, len(doc[i].get_text().strip()))
doc[i].get_pixmap(dpi=140).save(f"p{i+1}.png")   # then read the image
```

**The syllabus's grading table and schedule are on different pages, and they read
differently.** The syllabus is 2 pages: page 1 carries the class times, instructor, TAs,
the grading split with each exam's chapter scope, and the chapter/lab outlines; page 2
carries the week-by-week date table. Page 1's text layer extracts (~1,000 characters) but
its grading block reads better from the rendered image; page 2's date table extracts
cleanly as text. The seating chart, by contrast, has no usable text layer at all — that one
does need the render path.

So the rule is not 「render everything」 but **render the page whose content you actually
need and whose text layer did not give it to you** — a page that extracts is not
unreadable, and a page that extracts partially may still be hiding a figure.

That split matters because **the grading table's scope and the date table resolve an
ambiguity the grading table alone cannot.** A scope printed as `Chap. 1 ~ 4 or 5` is settled
by the schedule: the branch naming a chapter taught after the exam date cannot fire. Read
BOTH pages — the scope line without the schedule beside it leaves the branch unresolved, and
the schedule without the scope line says nothing about what is examined.

### An attachment filename is not an identity — check the first page

The attachment cache holds several courses' files side by side, and the names collide with
the courses' real chapter structure: `<CH-N>_note.pdf` through `<CH-N>_note.pdf` were all
**a course** notes (a textbook's chapter decks plus the instructor's handwritten pages),
`Chapter1_v1.pdf`/`Chapter2_v1.pdf` were **a course**, and three `<TERM>-mid*.pdf` files
were byte-identical copies of **a course一**'s midterm paper — none of them the circuits
notes their filenames imply.

Identify by opening page 1, never by name. Two cheap checks, because the failure is silent
— the file opens fine, it is just the wrong subject:

```bash
md5sum <candidate files>          # byte-identical copies collapse to one hash
```

```python
import pymupdf
d = pymupdf.open(f); print(d.page_count, d[0].get_text()[:120].replace("\n", " | "))
```

The subject line on page 1 is the only reliable identity, and for handwritten pages with
no text layer, render page 1 and read it. Report the identity table to the student — the
mapping of 「which file is actually this course's」 is itself the deliverable, because
every later session that opens the cache will otherwise open the wrong file.

### `/assignments` is the homework roster — the syllabus is not

**CLI flag: `--list-assignments`.**

The syllabus is a **plan**; `/assignments` is the **record**. A course syllabus
routinely names homework that does not exist yet: 「助教作業講解(Exam I+hw5-6)」
on a schedule line is the instructor's intention for a later date, not a
published assignment. Treating it as a to-do list produces a phantom gap
(「HW5 是缺的,怎麼辦」) for a file that has not been assigned.

`GET /api/v1/courses/{id}/assignments` returns the authoritative list with
`due_at` (UTC), `submission_types`, and `published`. For one course it held
four rows — HW1–HW4 — while the syllabus referenced HW5 and HW6. The modules
endpoint confirmed it: module `作業解答` held exactly HW1–HW4 solution PDFs,
one per assignment.

**Report the assignment list as the count it actually is.** 「Cool 上只有 HW1–HW4,
沒有 HW5」 is a finding; 「HW5 沒有 PDF 所以缺了」 is a wrong claim about a
homework that was never assigned.

### A homework set with no course coverage is a scope gap, not a task

When `/assignments` stops at HW4 and the textbook/chapter runs further, the
tail sections of the exam's chapter range have **no homework coverage**. That
is worth stating explicitly to the student: those sections must be studied
from the slides alone, which changes how they spend the last day. Do not
silently drop them (the syllabus says the chapter) and do not invent an
assignment for them.

**Do not conclude a file is missing from the Files tree.** Enumerate assignments
and modules before reporting anything as absent — for CA3, all three of Files
tree / announcement attachments / local disk came up empty, and the handout was
sitting in the assignment description the whole time.

### The handout's own test file decides the build, not the .cpp files

`TestDList.cpp` in DS CA3 does `#include "LockDList.cpp"` but does **not**
include `DList.cpp` or `DListNode.cpp`. The template definitions of
`DList<int>` are therefore never visible in that translation unit, and the link
fails with `undefined reference to DList<int>::DList()` even though every
`.cpp` is compiled.

Fix that works whether the grader compiles the files separately or `#include`s
them into one translation unit — explicit instantiation at the end of each file:

```cpp
template class DList<int>;
template class DList<double>;
template class DList<char>;
template class DList<std::string>;
```

### Assignment metadata worth capturing

`/assignments` also gives the grading terms, which the announcements omit:

- `due_at` is UTC (`2026-10-23T13:00:00Z` = 21:00 Taipei) — do not read it
  as a local time
- `submission_types` distinguishes `online_upload` (CA) from `on_paper` (HW)
- `desc` carries the handout link; `attachment` is **null** on these
  assignments, so `assignment["attachment"]` is not the way to find the file
- `lock_at` is where the upload window actually closes (see § submissions/self)

## Filing the result — announcements become inbox tasks, never the active list

Fetched announcements contain deadlines, and it is tempting to convert each one into a
task. **Do not.** Under the rule this repository recommends: a task the agent inferred from a source it
read — a deadline in an announcement, a 「hard blocker」 — goes to an **inbox** with
`reviewed_by_human: false` plus the reasoning and the questions needing a ruling.
Only work the user named or approved goes to your active task list.

The split that makes this cheap:

| destination | what lands there |
|---|---|
| `~/captures/ntu-cool-<slug>-<date>.md` | the announcement text — one file per course, all of it, unfiltered |
| a capture folder inside the notes system | the same file again, because a deadline in it is an action item and must be readable from wherever the tasks live |
| an inbox folder | one task per inferred deadline, awaiting a ruling |

The duplicated capture file is deliberate, not a mistake: the study record and the
action record are kept apart. A source that matters to both belongs to both.

Two facts to carry into the report rather than into a task body as settled:

**a course with zero announcements this term may still have all its material**, in the
Files tree and on disk already — check your notes and your downloads before treating a
missing announcement as a gap. A task whose
stated premise is 「unknown」 when the answer was already on disk is worse than no task.

**a deadline in an announcement is not automatically an action item.** Same reasoning,
different source: an announcement states a date, the decision to act on it is his. That
is what an inbox is for.

Do not run a Flask daemon. It is a second always-on service for a one-endpoint
need, and it pulls in an ORM the pinned versions cannot support on this interpreter.

### A fact copied N times drifts N ways — generate the table, check mechanically

A course fact (exam date, scope, submission deadline) gets copied into many vault
files: the capture folder, the operation log, the concept, entity, task, project and
overview pages, and the index. Every copy is written by hand, and nothing keeps them equal.

Measured 2026-10-23 on a real vault (751 wiki pages):

| fact | copies |
|---|---|
| <COURSE> 期 midterm | 16 |
| <COURSE> 期 midterm | 29 |
| <COURSE> 期中考一 10/14 | 11 |
| <COURSE> 期 midterm | 7 |

One moved deadline had reached 9 files; one wrong exam scope had reached 7.
**The cost of a correction is the copy count, not the edit.**

The fix is not "be careful" — it is a generated table plus a mechanical comparison:

```
fetch_courses.py    → data/course_facts.json  (gitignored, rebuildable)
drift_check.py      → scans live pages, reports mismatches, edits nothing
cron                → refresh + check every morning
```

Two design rules that matter:

1. **The table is a build artifact, not a page.** Put it in the same place as the
   other generated data (`data/*.json`, gitignored). A hand-maintained "source of
   truth" page is just one more copy to drift.
2. **The checker reports; it does not fix.** It cannot tell whether a line asserts
   a fact or narrates a change to it, so the verdict is his.

**Exclude the capture folder and the operation log.** They are append-only history, and "we used to
believe HW2 was 10/30" is *correct*. Counting them produces a report full of
false alarms, and a report that is always noisy is a report that gets ignored.

**Four false-positive guards, each learned from a real false positive:**

| symptom | guard |
|---|---|
| 「HW1」 exists in three courses with different dates | a name shared by several courses requires the *line* to name the course |
| 「期中考」 is generic | generic exam names (期中考/期末考/模擬考) are ALWAYS ambiguous |
| 「10/23 → 10/30」 narrates a change and is correct | lines with →/改成/原為/修正 are not drift |
| a date inside a capture file's name is a filename | strip path tokens before matching |
| 「我先前寫…是錯的」 quotes the stale value | lines with negation/correction wording are not drift |
| 「due 10/29、lock 10/30」 states two different facts | a `lock_at` date is not a `due_at` date |

A checker that reports zero must be *proven* to detect drift: inject a known-stale
value into a live page, confirm it fires, revert. A checker that has only ever
reported "clean" is untested.

### The scope you cannot fetch is the scope you must read

Some exam scope is not in the API at all. For <COURSE>, the scope had to be
derived from the syllabus's per-week `Reading -> G.T.M.: pp. X~Y` lines, and
**mapping page ranges to chapters needs the book's own running headers**, not its
table of contents:

```python
# for each range, read the first and last page's running header
# "9.2.2 Hash Functions" / "Chapter 5. Stacks, Queues, and Deques"
doc = pymupdf.open(book)
hdr = doc[printed + offset].get_text().split("\n")[0]
```

The TOC parse failed on a 738-page PDF (the dot leaders and page numbers are
extracted in an unusable order), and the first header-based attempt produced
false chapters because it matched a number at the top of any page. Reading the
header of a *known* page and confirming the range's endpoints against it is what
made the mapping trustworthy.

**The result is worth checking by hand, because a wrong scope is silent.** The
header-based mapping found that the recorded midterm scope (5 chapters) was
missing three: Stacks/Queues (Ch5), Trees (Ch7), and Memory Management (Ch14).
Ch14 is the one that is easy to lose — it is the W6 reading, a six-page range
(666-671) inside a chapter about garbage collection, sitting in a week titled
「Binary Search and Inheritance」 where nobody expects it.

### The roster answers 「what year is he in?」 without asking

The current-term roster is a read-only fact about which academic term the
student is in, and the term label is right there in the homepage JSON
(`"term": "115-1 (2026 Fall)"`). A course set that is unmistakably a
particular stage (junior-level engineering courses, not capstone-level ones)
cross-checks the term.

**Use it as an independent cross-check, not as the primary source.** The
student ID's year digits and the course roster are two different routes to the
same answer; agreement between them is what makes the answer a fact rather
than a coincidence of one bad lookup. When they disagree, the disagreement is
the finding — report which reading each source supports instead of picking
one.

**The roster sweep also answers 「what did he already hand in?」 in one pass.**
`--list-submissions` over every current course returns each assignment's
`workflow_state` — so it covers the assignments that are *not* in any
announcement, and the graded ones alongside the unsubmitted ones. That makes
it the cheap way to discover both a finished submission (so you stop telling
him to do it) and a missed one (so you do not).

### The `submission_types` field tells you whether it can be done online

`submission_types` distinguishes `online_upload` (upload before the
`lock_at`) from `on_paper` (hand it in physically, to a person, at a place).
The two have completely different failure modes, and a plan that treats an
`on_paper` assignment as an upload will be wrong about the deadline: the
physical hand-in has to happen while someone is there to receive it, which is
a wall-clock constraint the API's `due_at` does not capture. Report the
distinction explicitly, and when an `on_paper` item shares a date with an
online item, the physical one is the one to schedule first.

Two facts to carry into the report rather than into a task body as settled:

**a course with zero announcements this term may still have all its material**, in the
Files tree and already downloaded. Check the local captures before treating a missing
announcement as a gap. A task whose stated premise is 「unknown」 when the answer was
already on disk is worse than no task.

**a deadline in an announcement is not automatically an action item.** Same reasoning,
different source: an announcement states a date, the decision to act on it is the
user's. That is what an inbox is for.

Do not run a Flask daemon. It is a second always-on service for a one-endpoint
need, and it pulls in an ORM the pinned versions cannot support on this interpreter.

## Reference

- `references/api-findings.md` — the platform's real response shapes, the pagination
  contract, the User-Agent filter, the credential shape, and which claims are
  verified against the live site versus inferred.
- `references/ceiba-unreachable.md` — why Ceiba is not implemented: connect timeout with
  a passing control test, and what that rules in and out.
- `references/computer-assignment-retrieval.md` — how to get a CA handout when the
  Files tree is empty, including the two-hop download and the signed-URL rule.
- `references/manifest-status.md` — what "did we fetch this?" can mean without a
  manifest, and why the absence of one is a deliberate trade.
- `references/testing-and-interpreters.md` — **read before changing the script.** Test with
  the same interpreter the user will type; `requests` is the only third-party import and
  that is deliberate; the stdlib swap caught a real first-form-vs-trap-form bug.

## Pitfalls

- ❌ Don't report 「no attachments」 from an announcement sweep. The body never carries
  the file list; the Files tree does. On the current term that is the difference between
  0 files and 96 (91 in the tree, 5 bound to announcements).
- ❌ Don't walk `/courses/{id}/folders` and recurse. It is a flat list at every depth,
  so every non-root folder gets counted two or three times.
- ❌ Don't assume one page is the whole list. Canvas defaults to `per_page=10` and caps
  the parameter — 27 of 91 files were missing that way, with nothing to notice.
- ❌ Don't rely on `/folders/root` alone. It 403s on a non-credit course while the list
  endpoint still answers; falling back to the parentless entries keeps the course.
- ❌ Don't compose API paths for the Files tree. `/api/v1/courses/{id}/files` is the
  obvious guess and it 404s. Read `files_url` / `folders_url` off the folder objects.
- ❌ Don't trust a download's status code. An expired signed URL returns 200 with the
  login page; check magic bytes.
- ❌ Don't file an image-only PDF as unusable because extraction returned nothing. Render
  it and read the image — that is how a 0-character quiz-scope worksheet becomes a
  readable problem statement.
- ❌ Don't put a file's signed `url` in a report, a log, or a commit. It authenticates.
- ❌ Don't download straight into a working notes collection. Stage it, list it, and let
  the filing decision stay his.