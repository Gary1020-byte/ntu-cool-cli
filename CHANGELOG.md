# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-23

First release. The tool is a read-only fetcher for NTU Cool course announcements
and course files.

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
- `references/` — upstream findings, the Ceiba reachability control test, and
  the venv-vs-system-Python trap.

### Fixed

- Pagination silently dropped ~30% of files. The cursor was read from the
  wrong field, so a page of results was skipped.
- The JSON prefix was hardcoded as `r.text[9:]` with no documented reason. The
  parser now anchors on the first `{` or `[`, so a prefix may exist or not.
- A false claim in `ACKNOWLEDGEMENTS.md` about the upstream project.
- The author's own course roster was removed from every tracked file.

[Unreleased]: https://github.com/Gary1020-byte/ntu-course-announcements/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Gary1020-byte/ntu-course-announcements/releases/tag/v1.0.0
