# Manifest status — "did we fetch this?" without a database

`ntu_fetch.py` is intentionally stateless. It has no SQLite, no dedupe store, no
"last run" timestamp. That is a design choice (the digest pipeline already owns
storage, dedupe, and delivery — adding a second store creates two sources of
truth for the same artefact). But "is this file fetched?" has three independent
meanings, and the lack of a manifest makes each of them a manual answer today.

## The three things "fetched" can mean

| question | how to answer today | what proves it |
|---|---|---|
| **Existence** — does the file exist on disk? | `find <files-out> -name '*.pdf' \| wc -l` or per-course `ls` | the path itself |
| **Version** — is the on-disk copy the current one? | compare on-disk `size` (and `mtime`) against the API row's `size` and `modified_at` | the API's `size` and `modified_at` fields, returned in every file dict |
| **Content identity** — is the bytes-for-bytes content the same as last time? | `sha256` of the on-disk file vs the sha recorded the first time | a stored hash somewhere — **the script does not store one** |

Existence is easy. Version is a single round-trip and a `diff`. Content identity
without a manifest is "re-download and compare" — which is exactly what the
script does today, every run.

## Why the absence of a manifest is a deliberate trade, not a missing feature

A manifest file (JSON of `{file_id, sha256, size, mtime, fetched_at, local_path}`
per record) is small, git-friendly, and trivially diffable. The cost is that
**it creates a second source of truth** — the manifest says "fetched" and the
file path says "present" and the two can drift if a file is moved, deleted
locally, or partially re-fetched. A second store that can disagree with the
first is usually worse than no second store, especially when the file paths
already encode the same data.

The upstream repo the skill replaced had both: a SQLite model with
`sha1(crawler + classname + title + content + date)` as the dedupe key, and a
`present` flag for soft delete. Both are good design — see
`upstream-findings.md` — but they come with the daemon, the migration surface,
and the maintenance cost. The skill's verdict: *adopt the design idea, defer
the daemon until "fetch" actually runs more than once in a term.*

## What to do when a user asks "did we already fetch this?"

Run the existence query first (`find` / `ls`). If the file is there, compare
its on-disk size to the API's reported size in a single authenticated call:

```python
import json
sys.path.insert(0, '.../scripts')
import ntu_fetch as N
creds = N.load_credentials('~/.ntu-creds.json')
with N._session() as s:
    s.headers.update({'User-Agent': N.USER_AGENT})
    N.cool_login(s, *creds)
    files = N.fetch_course_files(s, <course_id>)
    for f in files:
        on_disk = Path(f'<files-out>/{f["id"]}/...').exists()  # path rule from SKILL.md
        same_size = on_disk and (Path(...).stat().st_size == f['size'])
        # that answers existence + version
```

This is one round-trip and a `stat` per file. The script's `dest` path already
embeds `file_id`, so the lookup is a single `Path` check, no name matching.

**Content identity** still requires a hash store, and the skill deliberately does
not have one. If a user actually needs byte-level "same as last time", the
honest answer is "re-download and compare against the file we have" — slow, but
correct, and the magic-bytes check on the download already filters out the
"HTTP 200 with login page" case so the comparison is meaningful.

## When to add a manifest

Add one the moment a `cron` (or any scheduled run) calls this script more than
once per term. Until then, the path-based existence check is enough, and a
second store is overhead.
