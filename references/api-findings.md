# Platform findings — what NTU Cool actually returns

Everything here was measured against the live site. Each entry is a fact about
the **platform**, not about any particular implementation, so it stays true
regardless of who reads it.

## The API base is alive and gated properly

```
GET https://cool.ntu.edu.tw/api/v1/courses   → HTTP 401
body: {"status":"unauthenticated","errors":[{"message":"需要使用者授權"}]}
```

401 with a structured body, not 404 — the endpoint exists and is gating
correctly. A 404 would mean the platform had moved.

## The response carries a prefix

A fixed-offset parse like `json.loads(r.text[9:])` is fragile, because the
prefix length is not part of any contract and the error body is a different
shape entirely:

```
json.loads(r.text[9:])  against the 401 body
  → :\"unauthenticated\",\"errors\":[{   →  JSONDecodeError
```

`ntu_fetch.py` anchors on the first `{` or `[` instead, so a prefix may be
present or absent. See `parse_json_loose()` and its tests.

## A cursor, not a page count

Canvas list endpoints cap `per_page`, and the bare call defaults to 10.
Measured 2026-10-18: one course's folder held 29 files and the
unparameterised call returned 10 — 19 files silently missing, with no error
and no empty-looking tail. 27 of 91 files across a term went missing that way.

Follow `Link: <...>; rel="next"` rather than assuming a page count. That is
the only pagination contract the API actually honours. See `_paged_get()`.

## Four stores, and the obvious one is often empty

| store | endpoint | holds |
|---|---|---|
| assignment description | `/assignments` → `data-api-endpoint` | CA handouts, homework sets |
| modules | `/modules` → `/modules/{id}/items` | lectures, week-grouped |
| Files tree | `/folders` → `files_url` | course files (can be nearly empty) |
| announcement attachments | `/discussion_topics` → `attachments[]` | files bound to one announcement |

For a CS course the Files tree held exactly one file, while two CA
archives were absent from it, from the announcement attachments, and from
every module — and were in the assignment descriptions the whole time. See
`computer-assignment-retrieval.md`.

## Ceiba is a different shape

Ceiba's announcement tables are parsed positionally:

```python
rows[0].find("td").string   # title
rows[1].find("td").string   # date
rows[5].find("td")          # content
```

Hard table indices. Any added or removed row silently mis-assigns fields — a
title landing in the body, or an exception from a vanished row. If Ceiba is
needed, verify against a live page before trusting the output. From this host
Ceiba does not respond at all; see `ceiba-unreachable.md`.

## The User-Agent filter

cool.ntu.edu.tw and adfs.ntu.edu.tw reset the connection at the TCP level when
the User-Agent contains `python-requests`. Measured 2026-10-21, same host,
same URL, same TLS stack, minutes apart:

| User-Agent | result |
|---|---|
| `curl/8.18.0` | HTTP 200, 10847 bytes |
| `Python-urllib/3.12` | HTTP 200 |
| `Mozilla/5.0` | HTTP 200 |
| `python` | HTTP 200 |
| *(empty)* | HTTP 200 |
| `python-requests/2.32.5` | **ConnectionResetError(104)** |
| `curl/8.18.0 python-requests` | **ConnectionResetError(104)** |

The filter matches the token **anywhere** in the header, so prefixing a
browser UA onto the default does not help. The failure is a TCP reset during
the request, not an HTTP status — which is why it reads as "the host is down"
rather than "we are being filtered". Retrying cannot fix it.

Diagnostic that separates the two in one command:

```bash
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 https://cool.ntu.edu.tw/login/saml   # 302
python3 -c "import requests; requests.get('https://cool.ntu.edu.tw/login/saml', timeout=20)"  # reset
```

Same minute, same host, different client — that is a UA filter, not an outage.

## Two design patterns worth keeping

Neither is a dependency; both are ideas to copy when a persistent store is
actually wanted.

- **Dedupe by content hash, not URL.** `sha1(source + title + content + date)`
  as a unique key. URLs change; content identity does not.
- **Soft delete via a presence flag.** Each run flips every `present=True` row
  to `False`, then re-saves what it just fetched. Rows survive, so history is
  retained and "what was live last week" stays answerable.

Both belong to a store. `ntu_fetch.py` has none — it writes Markdown and
exits, and storage, dedupe, and delivery belong to whatever runs it. See
`manifest-status.md` for what "did we fetch this?" means without a manifest.

## Credentials

Plaintext in a config file is the common shape:

```yaml
ntu_user: "bXXXXXXXX"   # 學號格式
ntu_pass: "123456789"
```

`ntu_fetch.py` takes credentials from the environment or a `--cred-file` path
instead, and refuses to read a credential file with loose permissions — a
world-readable credential file is a leaked credential.
