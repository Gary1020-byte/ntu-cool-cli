# Exam scope and course material — files, attachments, charts, identity

Getting at the material an exam is drawn from, and reading it correctly: the
Files tree's lock states, announcements versus attachments, seating charts,
encrypted PDFs, and telling one course's file from another's.

Read this when the question is 「範圍是什麼」「那份檔案在哪」「我的位置是哪」。

---

## An empty `url` on a file means two different things

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

## A solution file can be locked until a future date

`GET /api/v1/courses/{id}/files/{file_id}` returns `unlock_at`, `lock_at`, `locked`,
`hidden_for_user`. On a course, a solutions PDF existed with
`unlock_at: 2026-10-23T01:00:00Z` (台北 10/23 09:00) — **the signed `url` came back empty
and the download was not possible yet**. An empty `url` on a file you can see in the
Files tree means "not released yet", not "download is broken". Check `unlock_at` before
concluding the file is missing.

**A locked course key is not a reason to wait.** The course's own solution PDF unlocks
at a future hour, but the **textbook's published solutions manual** is available now and
carries the same answers — for concept questions it carries the *prose* answer, not just
a number. When a homework set needs solving, go get the manual rather than polling for
`unlock_at`. Recipe: `course-assignment-submission/references/textbook-solutions-manual-and-verification.md`.

## A locked file's `url` field is empty — fetch the metadata, not the tree entry

The Files-tree entry and the file-metadata response are different shapes. A tree entry
may carry a `url` that is present-but-unusable, while the metadata response
(`GET /api/v1/courses/{id}/files/{id}`) carries `display_name`, `size`, `unlock_at`,
`lock_at`, `locked`, `hidden_for_user` — the fields you need to decide *why* a download
is not possible. Fetch metadata for every file you intend to download rather than
relying on what the tree listing happened to include.

## `discussion_topics` needs `only_announcements=true` or it returns `[]`

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

## Announcement attachments carry the exam logistics

`/discussion_topics` items include `attachments[]` with `display_name` and `id`.
The a course 期中考 announcement (posted 5 days before the exam) carried
`期中考教室座位表.pdf` — the seating chart, which is the only place the room
split is published. (The generic Chinese name is fine; it is a real file's
title, not a personal one.) Download it via the two-hop file fetch, not by guessing a path.

## A course code and a student ID differ by one letter — check which one you have

NTU ESOE course codes are six digits (`<SIX-DIGIT-CODE>` / ESOE `<CODE>`) and
appear in the handout's own header line, so they are trivially mistaken for the
student ID (`B` + eight digits). The two are used in different places and neither is
guessable:

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
said `CA1R<STUDENT-ID>.zip` (with an `R`); the two archives the grader had actually
accepted were `CA1BXXXXXXXX.zip` and `CA2BXXXXXXXX.zip` (no `R`). The document and the
grader disagree, and the grader wins.

## A seating chart is a lookup, not a diff — and "not found" is ambiguous

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

The room is the heading on that page (「<ROOM> 教室座位表」), and the
row's horizontal order gives the seat.

**A miss is ambiguous between "wrong ID" and "not on the chart"** — so before
reporting that a student is not on a chart, confirm you searched for the ID and not
for a course code. A chart of ~66 IDs with no hit for a value that is visibly a
course code is a finding about the *value*, not about the student.

## Two seating-chart shapes — read the chart type before reading the chart

A seating chart comes in two shapes and they need different parsers. **Type A**
lists student IDs placed in seat positions (the room is the page heading; find the
ID, reconstruct its row from word coordinates). **Type B** is a floor map of seat
numbers plus a separate 梯次表 whose rows are seat numbers and whose cells are
student IDs — so ID → seat number → time slot comes from the table, and seat
number → physical place comes from the map, which needs a render and a vision
read.

**One course can publish one chart per exam** (a paper-midterm chart and a lab
chart days later). They are different documents with different keying; answering
one exam's seat from the other chart is wrong. And **the chart is not the venue** —
a lab exam's room came from an earlier announcement, not from the chart, so name
that announcement as the venue's source.

Full recipe, coordinate code and reporting shape: `references/seating-chart-lookup.md`.

## PDFs may be password-protected — render and read the image

A course's syllabus PDF and its class-notes PDF (both encrypted) open with
`is_encrypted=True`. The lab-notes password (published in a
course announcement, so it is course-specific and not a secret of the tool)
authenticates the syllabus and class notes (`d.authenticate(PASSWORD)` → 6 =
success) but **not** the seating chart.

Unlock first, then measure each page — a partially-extractable document is the case that
misleads:

```
doc = pymupdf.open(path); doc.authenticate(PASSWORD)   # from the course's announcement
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

## An attachment filename is not an identity — check the first page

The attachment cache holds several courses' files side by side, and the names collide with
the courses' real chapter structure: `<CH-N>_note (1).pdf` through `<CH-N>_note.pdf` were all
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

