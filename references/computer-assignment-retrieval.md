# Getting a Computer Assignment handout off NTU COOL

The handout for a CA is usually **not** in the course Files tree. Measured
2026-10-21 on a CS course (course <COURSE_ID>): the Files tree held exactly one
file (`<PREFIX>_CA1.pdf`), while `<PREFIX>_CA2.zip` and `<PREFIX>_CA3.zip` were
absent from it,
from announcement attachments, and from every module — and from the local disk.
All three were on Cool the whole time, inside the assignment descriptions.

## Recipe

```python
import re, sys
sys.path.insert(0, "<skill>/scripts")
import ntu_fetch as nf

creds = nf.load_credentials("~/.ntu-creds.json")
s = nf._session()                       # sets the User-Agent; see SKILL.md
nf.cool_login(s, *creds)
API = f"{nf.API}/courses/{course_id}"

for a in nf.parse_json_loose(s.get(f"{API}/assignments",
                                   params={"per_page": 100}, timeout=30).text):
    m = re.search(r'data-api-endpoint="([^"]+)"', a.get("description") or "")
    if not m:
        continue
    meta = nf.parse_json_loose(s.get(m.group(1), timeout=30).text)   # hop 1: JSON
    res = nf.download_file(s, meta["url"], dest, magic)              # hop 2: bytes
```

`hop 1` answers `application/json` — `{"id":<FILE_ID>,...}` — **not** the file.
The signed `url` is inside it. A direct `download_file()` against the
`data-api-endpoint` fails with "magic mismatch", which reads like a corrupt
file but is the wrong endpoint.

## Modules

```python
for m in nf.parse_json_loose(s.get(f"{API}/modules",
                                   params={"per_page": 100}, timeout=30).text):
    for it in nf.parse_json_loose(s.get(f"{API}/modules/{m['id']}/items",
                                        params={"per_page": 100}, timeout=30).text):
        if it.get("type") == "File":
            meta = nf.parse_json_loose(s.get(it["url"], timeout=30).text)
            nf.download_file(s, meta["url"], dest, magic)
```

Same two hops. A module item's `url` is an API link, not a download link.

### The file id in an assignment description can be dead while the Files tree has the file

Measured 2026-10-23 on a CS course (course <COURSE_ID>): the CA1 assignment description
links `data-api-endpoint=".../files/10140359"`, and **`GET /files/10140359` returns
404** — "The specified resource does not exist." The same file, `<PREFIX>_CA1.pdf`, is
reachable in the course Files tree under a **different** id (`<FILE_ID>`), and that
one downloads fine.

The assignment description's link was pointing at a replaced file object, not at
the current one. So a 404 on the description's file id is **not** evidence the
handout is gone — and it is not evidence the assignment description is broken
either. Report it as "the description's link is stale", and resolve the real file
from the Files tree or the modules by `display_name`.

Two ids, one name:

| source | id | result |
|---|---|---|
| CA1 assignment description | 10140359 | **404** |
| course Files tree | <FILE_ID> | 200, downloads |

**Never conclude a handout is unavailable from a single id.** Enumerate every store
(`/assignments` descriptions, `/modules` items, Files tree) and match on
`display_name` before reporting absence.

## The submission endpoint (for reading state, not for uploading)

The submission API is the one place that answers 「我有沒有交」, and it is also where
the upload itself would go. **Both halves live here — know both, use only the first.**

```
GET  /api/v1/courses/{id}/assignments/{aid}/submissions/self   → 200, your submission
GET  /api/v1/courses/{id}/assignments/{aid}/assignments/...    → 404 on the wrong path
POST /courses/{id}/assignments/{aid}/submissions               → the upload (HTML form)
```

`OPTIONS` on the submissions path returns **404** — that is not "the endpoint is gone",
it just means OPTIONS is not routed. The API path only answers GET.

### The upload is a Rails web form, not the API

`GET /api/v1/courses/{id}/assignments/{aid}` returns the assignment JSON and a
`description`, but the actual upload form lives in the **HTML page**, and you have to
ask for HTML to get it — the same URL with the default `Accept` header returns
**HTTP 400 `endpoint does not support ''`** (26 bytes) and looks like the assignment
is missing. With `Accept: text/html,...` it returns 200 and ~52 KB of page.

```
form action = /courses/{id}/assignments/{aid}/submissions   (POST, multipart/form-data)
fields: authenticity_token (from the page) + submission[submission_type]=online_upload
        + submission[attachment_ids] + submission[comment]
```

**The API JSON cannot produce a valid upload.** It carries no `authenticity_token`,
so a POST built from API fields alone fails the CSRF check.

### The fields that tell you whether an upload will even work

```
locked_for_user          → false = the window is open; true = the student cannot upload
allowed_attempts         → -1 = unlimited submissions (re-upload replaces the old one)
can_duplicate            → true = the assignment allows more than one submission
lock_at                  → the real deadline (UTC); after this, upload is refused
allowed_extensions       → when present, a .zip that is not on the list is rejected
```

`due_at` is the *graded* deadline; `lock_at` is where the upload window closes.
On a CS course CA3 (2026-10-23): `due_at 2026-10-23T13:00:00Z`, `lock_at
2026-10-26T13:00:00Z` — a 3-day grace window. `locked_for_user: False` and
`allowed_attempts: -1` confirmed the upload would have been accepted.

### Read state without ever creating state

`workflow_state` is `unsubmitted` / `submitted` / `graded`, `attachments` is `None`
until a file is attached, and `attempt` is `None` before the first upload. **A GET
never creates a submission** — probing these is free and leaves nothing behind.

The risk is a half-finished upload: a POST that timed out or errored after the file
was accepted leaves `attachments` set but `workflow_state` still `unsubmitted`. That
is the state to check for and clear before retrying, because `allowed_attempts: -1`
means the retry replaces rather than stacks.

## What the assignment endpoint also tells you

| field | use |
|---|---|
| `due_at` | UTC. `2026-10-23T13:00:00Z` = 21:00 Taipei. |
| `submission_types` | `online_upload` (CA) vs `on_paper` (HW) |
| `description` | holds the handout link |
| `attachment` | **null** on these assignments — not the way to find the file |

## Verifying you got the real file

`download_file()` already checks the magic bytes, but confirm the size against
the `size` field in the hop-1 JSON, and unzip a `.zip` to confirm the entry
count. A 200 that carries the login page is answered for an expired signed URL
— the magic check is what catches that.

## A compile error in a handout is the student's, not the tool's

A C++ handout can fail to link for reasons that have nothing to do with fetching
it — a test file that `#include`s one source but not the others is a classic
case, and the fix (explicit instantiation at the end of each `.cpp`) is a
course-level answer rather than a retrieval one.

The tool's job ends at delivering the bytes. Debugging a student's handout
belongs to the assignment workflow, not here.
