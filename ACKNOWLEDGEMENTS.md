# Acknowledgements

## brianbbsu/NTU-Announcement-Crawler

<https://github.com/brianbbsu/NTU-Announcement-Crawler> — created 2019-09-25.

This project exists because that one did. Reading its source is what made the
design of `ntu_fetch.py` possible: it documented the SAML login sequence and the
`/api/v1/courses/{id}/discussion_topics?only_announcement=true` endpoint, neither
of which is written down anywhere else.

**What was taken from it**

- the fact that NTU Cool answers to a JSON API behind a SAML login,
- the shape of the announcement list response.

Everything else was reverse-engineered against the live site in October 2026 —
the course-Files tree, the folder-object URL fields, the homepage roster parse,
the download magic check.

**What was admired but deliberately left out**

Two upstream design choices are good and are *not* in this repository: dedupe by
content hash rather than by URL, and a `present`-style flag for soft-deleting
rows whose source has disappeared. Both belong to a persistent store, and this
script has none — it writes Markdown and exits. They are recorded in
`references/upstream-findings.md` as the things to copy the day this stops being
one-shot and starts being a service.

**What was not taken**

No code. `ntu_fetch.py` is a ground-up reimplementation and shares no source
with the upstream file layout. The upstream repo has **no LICENSE file**, which
means all rights are reserved by default: its code cannot be redistributed.
Nothing was copied from it into this repository.

The upstream service layer — `config.py`, `models/`, `daemon.py`, `api.py`, the
Flask and SQLAlchemy stack, and the Telegram bot — was deliberately not adopted.
`references/upstream-findings.md` records the evaluation, including why the whole
service had to be rebuilt around a one-endpoint question.

**If you want the daemon**, use the upstream project directly. It does one thing
this one does not: it polls on a schedule and pushes new announcements to
Telegram. This repository only fetches, and only when you ask.
