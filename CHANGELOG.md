# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-10-23

### Added

- `--show-page <slug>` — one course page's content, as plain text: the title,
  the URL, and the body. Previously `--list-pages` gave only the slugs, so
  reading the syllabus meant a second API call by hand.
- `--download-handout` — downloads the handouts linked from assignment
  descriptions, under their real display names. The path is two hops: the
  endpoint answers with JSON describing the file, and the signed URL is inside
  it.

### Fixed

- **A bare `data-api-endpoint` value was passed to `requests` as a URL.** Some
  assignments carry a page slug (`ke-cheng-da-gang`) rather than an absolute
  API URL, and requests raised `MissingSchema` — the slug is not a URL. Now
  absolute-ised, and a page endpoint is reported as a page instead of being
  treated as a file to download.
- **`fetch_all_courses_historical()` is now clearly labelled as a trap.** It
  is not reachable from any flag — the CLI uses `fetch_courses()`, which
  parses the home page and returns only current-term courses. Measured
  2026-10-23 on a real account: 7 current courses against 10 from the
  historical endpoint, the extras being last term's plus three dead entries
  with `name: null`. Every one of them had `term: null`, so there is no term
  field to filter on afterwards. The docstring now says so.

### Credentials

- New tests assert the password never reaches the output: the login path is
  run against a failing session and the secret must not appear in stdout or
  stderr; `enable_http_debugging`, `debuglevel` and `response_hook` must stay
  absent (any of them would dump request bodies); a world-readable credential
  file is refused; the environment-variable path is accepted.
- The README gained a "Where the password can and cannot leak" section. The
  tool's own behaviour is safe on all four surfaces; the real risks are the
  credential file's *path* (shell history, process list), the signed download
  URLs, and the session cookies — which live only in the `requests.Session`
  and are gone when the process exits.

### Tests

79 now, up from 69.

## [1.2.0] - 2026-10-23

### Added

Five read-only CLI flags, so the capabilities the skill describes no longer
require writing API calls by hand:

| flag | what it reads |
|---|---|
| `--list-assignments` | `/assignments` — the homework roster: name, `due_at`, `lock_at`, points |
| `--list-submissions` | `/assignments/{id}/submissions/self` — your own status: unsubmitted / submitted / graded, score, late policy |
| `--list-pages` | course pages: syllabus, calendar, late-submission policy, submission instructions |
| `--list-modules` | modules — lectures grouped by week |
| `--list-handouts` | handout links in assignment descriptions, where CA material lives when the Files tree is empty |

Plus an **agent install prompt** in the README (English and Chinese) that
lists the eight capabilities and tells the agent to ask which ones are needed
before installing anything. A partial install is the normal case: the skill
describes stores the agent will never query, and each unused capability is a
way to answer a question from the wrong source.

### Fixed

- **`include[]=items` was not requested when listing modules.** Without it the
  API returns the module list with every `items` array empty — no error, just
  nothing. Measured against the live site: 8 modules and 0 items without it,
  46 items with it. `--list-modules` printed module names and nothing under
  them, and `--list-pages` printed nothing at all, because the page slugs
  only exist on the module items.

### Tests

69 now, up from 53. The new ones cover the assignments / submissions / pages /
modules / handouts readers, the `include[]=items` parameter, the
`/submissions/self` path (the list form `?self=1` returns 403), and a
read-only guard that asserts no fetch function issues a write — the only POST
in the file is in the SAML login chain, which is authentication, not a write.

## [1.1.0] - 2026-10-23

### Changed

- **Renamed to `ntu-cool-cli`.** The previous name, `ntu-course-announcements`,
  described only one of four things the tool reaches. It also fetches course
  files, CA handouts that live in assignment descriptions rather than the
  Files tree, and submission status. `cool` is how NTU students already refer
  to the platform, and `cli` says what kind of thing it is.
  - PyPI package: `ntu-course-announcements` → `ntu-cool-cli`
  - Console script: `ntu-cool` → `ntu-cool-cli`
  - The module stays `ntu_fetch`; `python3 scripts/ntu_fetch.py` still works.
  - GitHub redirects the old repository URL to the new one.
- `SKILL.md` now documents all four stores — announcements, the Files tree,
  assignment descriptions, and modules — with the submission-status endpoint,
  and the trigger list covers the file and submission cases, not just
  announcements.
- Synced three sections that existed only in the locally-installed copy of the
  skill: the User-Agent filter, exam scope in the worksheet pairing, and CA
  handouts in the assignment description.
- Added `references/computer-assignment-retrieval.md` and
  `references/manifest-status.md`.
- `references/upstream-findings.md` became `references/api-findings.md`. The
  content was about the platform's real response shapes — the pagination
  contract, the User-Agent filter, the credential shape — but it was written as
  a review of one particular project. It is now written as facts about the
  platform, which is what it actually measured. `ACKNOWLEDGEMENTS.md` keeps the
  attribution and the no-code-copied statement, which is the part that matters
  for licensing: that project carries no LICENSE file, so nothing from it may
  be redistributed.

### Fixed

- **The session User-Agent was never applied.** `USER_AGENT` was defined at the
  top of the script and then not set on the session, so every request went out
  with `python-requests/2.x`. cool.ntu.edu.tw and adfs.ntu.edu.tw reset the
  connection at the TCP level when that token appears anywhere in the header —
  which reads as "the host is down" rather than "we are being filtered".
  Retrying cannot fix it. Measured 2026-10-21: `curl/8.18.0` → HTTP 200 in the
  same minute that `python-requests/2.32.5` → `ConnectionResetError(104)`.
  Now set in `_session()`, so every hop of the SAML chain carries it.

## [1.0.0] - 2026-10-23

First release, under the name `ntu-course-announcements`. The tool is a
read-only fetcher for NTU Cool course announcements and course files.

### Added

- `ntu_fetch.py` — single script, one third-party dependency (`requests`).
  HTML parsing uses `html.parser` from the stdlib.
- `--probe` — unauthenticated reachability check for NTU Cool and Ceiba.
- `--list-files` — list the course file tree for a course.
- `--announcements` — fetch announcements for enrolled courses.
- `ntu-cool` console script via `pyproject.toml`.
- 53 offline tests. No network, no credentials, no login — they can never reach
  cool.ntu.edu.tw.
- CI on Python 3.9, 3.10, 3.11, 3.12.
- `SKILL.md` — the rulebook: verification status, traps, workflow.
- `references/` — platform findings, the Ceiba reachability control test, and
  the venv-vs-system-Python trap.

### Fixed

- Pagination silently dropped ~30% of files. The cursor was read from the
  wrong field, so a page of results was skipped.
- The JSON prefix was hardcoded as `r.text[9:]` with no documented reason. The
  parser now anchors on the first `{` or `[`, so a prefix may exist or not.
- A false claim in `ACKNOWLEDGEMENTS.md` about the project it was derived from.
- The author's own course roster was removed from every tracked file.

[Unreleased]: https://github.com/Gary1020-byte/ntu-cool-cli/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/Gary1020-byte/ntu-cool-cli/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Gary1020-byte/ntu-cool-cli/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Gary1020-byte/ntu-cool-cli/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Gary1020-byte/ntu-cool-cli/releases/tag/v1.0.0
