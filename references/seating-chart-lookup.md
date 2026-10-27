# Reading an exam seating chart — room, seat, time slot

The question 「期中考在哪間教室、我的位置是第幾排第幾個」 has three independent
answers, and they rarely live in one document. Identify each one's source before
answering.

## The three facts and where each comes from

| fact | source |
|---|---|
| date + time window | the exam announcement (may say 「下周二14:20-16:20」 — a *relative* day) |
| room number | the seating chart's per-page heading (「<ROOM> 教室座位表」 / 「<ROOM> 教室座位表」) |
| his seat | the chart, keyed by student ID |
| venue for a lab/practical exam | an *earlier* announcement (the lab location is not on the seating chart) |

**A course can publish one seating chart per exam.** A circuits course posted a
paper-midterm chart (2 pages = 2 rooms) and, days later, a lab-midterm chart (1 page).
They are different documents with different keying: the paper chart lists **student
IDs in seat positions**; the lab chart lists **seat numbers in a floor map** plus a
separate time-slot table. Never answer one exam's seat with the other chart.

**The chart is not the venue.** For the lab exam the chart carried only a 大門
marker; the room came from an earlier announcement naming the lab's physical
location. Say which announcement the venue came from.

## Relative dates in announcements

Announcements use relative day names (「下週四(10/29)早上」, 「下周二14:20-16:20」).
The parenthetical date is the fact; the relative word is decoration. Compute the
weekday with `date -d` before printing it — the skill's existing weekday rule
applies to announcement prose exactly as it applies to `due_at`.

## Chart type A — IDs placed in seat positions

Text layer has one ID per seat. Find the ID, then reconstruct its row and column
from word coordinates:

```python
import pymupdf
d = pymupdf.open("期中座位表.pdf")
for i in range(d.page_count):
    words = d[i].get_text("words")
    head = d[i].get_text().split("\n")[0].strip()   # room heading, e.g. "<ROOM> 教室座位表"
    hit = [w for w in words if w[4] == STUDENT_ID]
    if not hit:
        continue
    y = (hit[0][1] + hit[0][3]) / 2
    row = sorted([w for w in words if abs((w[1] + w[3]) / 2 - y) < 8],
                 key=lambda w: w[0])
    print(head, "row:", [w[4] for w in row])
```

The row's horizontal order gives the seat, but the chart's reading direction is
not guaranteed: in one 206-room chart the rows ran right-to-left in a serpentine
layout, so "row position 5 of 5" was **not** "leftmost". Report the seat by
**row identity and neighbours** (the row's ID list, his position within it) rather
than by "5th from the left" unless the coordinates prove the direction.

A multi-page chart is one room per page — the room heading is per page, so a miss
on page 1 says nothing about pages 2+.

## Chart type B — seat-number floor map + time-slot table

The lab chart has two regions on one page:

1. a **floor map**: numbered seats 1..N laid out in a grid, with 大門 (entrance)
   marked
2. a **梯次表**: rows = seat number, columns = time slots, cells = **student IDs**

So the student is found in the *table* region (ID → row → seat number → column =
time slot), and his physical place is found in the *map* region (seat number →
grid position).

```
梯次表 row 5 | 10:10-10:50: <ID-A> | 11:00-11:40: <ID-B> | 11:50-12:30: <ID-C>
→ seat number 5, slot 11:00-11:40
```

**The map needs a render, not just the text layer.** The seat numbers are
positioned in a grid with no table borders in the text; `get_text("words")` gives
coordinates for the numbers but not the grid cells. Render the page to PNG and read
it with the vision tool to state "which row/column of the map, next to which
neighbours". Coordinates alone do give a defensible answer (x/y clusters), but the
render confirms it.

## Reporting shape

Give both exams as separate blocks, each with: date + weekday (computed), time
window, venue, his exact seat, what to bring, and the source announcement. Then
one line stating that the two charts are separate documents so the seats are not
interchangeable.
