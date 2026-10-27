# Reading a course's state — submissions, pages, schedules, deadlines

What the course's own records say: whether you submitted, what the course
pages contain, which exams exist, and when a deadline actually is.

Read this when the question is 「我交了嗎」「有什麼要交」「期限是什麼」.

---

## Your own submission status lives at `/assignments/{id}/submissions/self`

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

## Course pages are addressed by slug, and the slug is on the module item

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

## The course calendar page carries exams that `/assignments` does not list

A course's 課程行事曆 page (`/pages/ke-cheng-xing-shi-li`) is a week-by-week
HTML table whose 主題 column names the exam and whose 課本範圍 column gives
the chapters. **It is a distinct source from `/assignments`, and it often holds
exams the assignment list never mentions.**

Measured: one course's `/assignments` listed only 期中考一, while its calendar
page carried 期中考一, 期中考二 and 期末考 — with the scope of each
(`midterm exam 1 / Chapters 1-3`, `midterm exam 2 / Chapters 4-6`,
`final exam / Chapters 1-9, 13`). Two of the three exams were invisible to an
assignment sweep.

Parse it as a table, not as prose — the page body is one `<table>` of
`<tr>/<td>`:

```python
import re, html
body = json.loads(r.text)["body"]
for tr in re.findall(r"<tr.*?</tr>", body, re.S):
    cells = [re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", c))).strip()
             for c in re.findall(r"<t[dh].*?</t[dh]>", tr, re.S)]
    if any(cells):
        print(" | ".join(cells))
```

The 截止 column of that table is the assignment tag of the week
(`HW#6`), **not** a due date — the due date still comes from `/assignments`.

## A course can have NO modules, NO pages, NO quizzes, and NO calendar

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

## A stored deadline goes stale — re-read `/assignments` before planning around any date

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

## A syllabus's week column is not a due date

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

## A deadline value can be right while its weekday label is wrong

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

