# Homework and due dates — the roster, the coverage, the hand-in

The homework record and the dates that go with it: what is actually
assigned, what a syllabus plans but never assigns, how a paper hand-in differs
from an upload, and the shape of a complete answer.

Read this when the question is 「作業啥時交」「有沒有漏的」「我交了沒」。

---

## `/assignments` is the homework roster — the syllabus is not

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

## A homework set with no course coverage is a scope gap, not a task

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

## Assignment metadata worth capturing

`/assignments` also gives the grading terms, which the announcements omit:

- `due_at` is UTC (`2026-10-23T13:00:00Z` = 21:00 Taipei) — do not read it
  as a local time
- `submission_types` distinguishes `online_upload` (CA) from `on_paper` (HW)
- `desc` carries the handout link; `attachment` is **null** on these
  assignments, so `assignment["attachment"]` is not the way to find the file
- `lock_at` is where the upload window actually closes (see
  `reading-course-state.md` § Your own submission status)

## 「X 作業啥時交」— the answer shape

This is the standing question, and it has a fixed answer shape. Give a one-line
headline first (date + clock + venue), then the sources that back it, then the
student's own status, then the policy, then adjacent facts you already have:

```
HW2：<YYYY/MM/DD>（週<W>）<HH:MM> 前，<ROOM>。
- 公告「HW2繳交」：延至 <YYYY/MM/DD> 週<W>繳交，<HH:MM>-<HH:MM> 到 <ROOM> 交，並取回 HW1。
- /assignments：due_at = ...Z = 台北 <HH:MM>，submission_types = on_paper。
- 你的 HW2 目前 unsubmitted — 還沒交。
- 作業規定：當周有作業要交，請上課前交給助教；來不及的，<HH:MM> 前到 <ROOM> 門口的收作業資料夾，逾時不候。
- 順帶：HW1 已 graded；期中考 <YYYY/MM/DD>（週<W>），範圍 <UNITS>。
```

Rules for this shape:

- **Four sources, and each adds something the others lack.** The announcement
  gives the venue and the hand-in hours; `/assignments` gives the UTC instant and
  the submission type; `/submissions/self` gives his state; the standing
  「作業規定」 announcement gives the fallback drop-box and the cutoff. A report
  with only the due_at is a date, not an answer.
- **Say his submission state in the same breath.** 「還沒交」 next to the date is
  the actionable half; a bare date reads as done.
- **On-paper assignments carry logistics the API cannot.** `submission_types:
  ["on_paper"]` means `lock_at` is usually `None` — the API has no upload window
  to close — so **a null `lock_at` is not a missing deadline**. The real deadline
  is the course's physical hand-in time, which lives in the announcement, and
  「逾時不候」 means there is no grace period to assume.
- **A postponed assignment moves in the announcement and in `due_at` together**,
  but the announcement is the one that states the *place and hours*. When both
  agree, report both; when the announcement moves the date, the live `due_at`
  wins for the instant and the announcement wins for the logistics.
- **The 作業規定 announcement is a standing rule, not a one-off.** Fetch it once
  per course and keep it: it explains 「上課前交給助教」 and the door drop-box,
  which resolves what the due time actually means for a paper assignment.

## Programmatic access to the same data

For 「今天有什麼交」 or a per-course due/submission table, use the module
directly instead of grepping CLI output:

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import ntu_fetch as nf

user, pw = nf.load_credentials(os.path.expanduser("~/.ntu-creds.json"))  # TUPLE
s = nf._session(); nf.cool_login(s, user, pw)

for c in nf.fetch_courses(s):                 # current-term roster, homepage parse
    for a in nf.fetch_assignments(s, c["id"]):
        print(a["name"], a.get("due_at"), a.get("lock_at"), a.get("submission_types"))
        sub = nf.fetch_own_submission(s, c["id"], a["id"])
        print("  ", sub.get("workflow_state"), sub.get("submitted_at"))
```

Helper signatures that bite if assumed:

- `load_credentials(path)` → `(user, password)` **tuple**, not a dict. A
  dict-shaped access raises `AttributeError`. **It does NOT expand `~`** — the
  credential file guard stats the raw path and raises
  `FileNotFoundError: '~/.ntu-creds.json'`. Pass
  `os.path.expanduser("~/.ntu-creds.json")` yourself.
- `cool_login(s, user, password)` — the login function is `cool_login`, not
  `login`.
- `fetch_own_submission(s, course_id, assignment_id)` → the submission dict.
- `fetch_courses(s)` → dicts with `id` and `longName`; `longName` may carry a
  trailing course-code suffix (「… - <COURSE-NAME> (ESOE<CODE>)」), so match on a
  substring, never equality.

## The scope you cannot fetch is the scope you must read

Some exam scope is not in the API at all. For one course, the scope had to be
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

## The roster answers 「what year is he in?」 without asking

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

## The `submission_types` field tells you whether it can be done online

`submission_types` distinguishes `online_upload` (upload before the
`lock_at`) from `on_paper` (hand it in physically, to a person, at a place).
The two have completely different failure modes, and a plan that treats an
`on_paper` assignment as an upload will be wrong about the deadline: the
physical hand-in has to happen while someone is there to receive it, which is
a wall-clock constraint the API's `due_at` does not capture. Report the
distinction explicitly, and when an `on_paper` item shares a date with an
online item, the physical one is the one to schedule first.

Two facts to carry into the report:

**a course with zero announcements this term may still have all its material**, in the
Files tree and already downloaded. Check the local files before treating a missing
announcement as a gap.

**an announcement states a date; whether that date becomes an action is the
caller's decision.** The tool reports what the course said and stops there.

Do not run a Flask daemon. It is a second always-on service for a one-endpoint
need, and it pulls in an ORM the pinned versions cannot support on this interpreter.

