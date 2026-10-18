# Upstream findings: brianbbsu/NTU-Announcement-Crawler

Evaluation date 2026-10-18. Clone was disposable (scratch, 24h prune). Nothing from this
repo is installed as a service.

## What the repo actually is

Five modules in a straight line:

```
config.py  -> crawl.py -> models/ -> daemon.py -> api.py
credentials  crawler    SQLite   Telegram    Flask
```

`main.py` = `start_daemon(600)` + `api.run()`. Crawls every 600 seconds and re-fetches
everything each time (`per_page=100000`); there is no incremental fetch.

Two design decisions worth keeping even if the repo is not adopted:

- **Dedupe by content hash, not URL.** `sha1(crawler + classname + title + content + date)`
  → `digest` unique column. URLs change; content identity does not.
- **Soft delete via `present`.** Each run flips every `present=True` row to `False`, then
  re-saves what it just fetched. Rows survive, so history is retained and "what was live
  last week" stays answerable.

## Verified on this machine

```
GET https://cool.ntu.edu.tw/api/v1/courses   → HTTP 401
body: {"status":"unauthenticated","errors":[{"message":"需要使用者授權"}]}
```

401 with a structured body, not 404 → endpoint alive, gating properly.

Storage and HTTP layer proven with synthetic data, no credentials:

```
save()                                  OK, digest assigned
re-insert same digest                   1 row (dedupe works)
get_text_content() on '<p>截止 10/20 23:59</p>'  → '截止 10/20 23:59'
present flag: mark-all-absent then re-save  →  0 then 1
GET /api/   → HTTP 200, 11 JSON keys
GET /       → HTTP 200, Jinja2 template renders
```

## Breakage chain on Python 3.14

Two independent failures, each cascading. These are findings about a 2019 repo meeting a
2026 interpreter, not about this environment.

**1. Flask 1.0.2**
```
ImportError: cannot import name 'Markup' from 'jinja2'
```
Flask 1.x imports `jinja2.Markup`, removed in Jinja2 3.x. Upgrading Flask to 3.1.3 fixes
the import, and both templates then load fine under Jinja2 3.1.6.

**2. SQLAlchemy 1.3.8**
```
AttributeError: module 'sqlite3.dbapi2' has no attribute 'version_info'
```
`sqlite3.dbapi2.version_info` was removed in Python 3.12. Upgrading to SQLAlchemy 2.1.5 hits
a second, deeper break:
```
TypeError: Mapper.__init__() got an unexpected keyword argument 'order_by'
```
SQLAlchemy 2.x removed mapper-level `order_by`. The upstream model carries:
```python
__mapper_args__ = {"order_by": (desc(date), pos)}
```
Ordering now belongs on the query — which `utils.py:16` and `api.py` must pass explicitly.
**Total patch surface: one file, one block, 4 lines.** Verified working afterwards.

The real adoption cost is this number, not the count of failing installs. Each "just upgrade
the pin" produced a fresh error.

## The `text[9:]` slice

`crawlers/NTU_cool.py:21` and `:53`, both:
```python
dt = json.loads(r.text[9:])
```

No documented reason for 9. Against the reachable 401 body it yields
`:"unauthenticated","errors":[{` → `JSONDecodeError`. Written 2019-10-25, the same commit
that added another crawler; most likely a one-off guard against a prefix that was present
at the time.

Mark **unverified, not broken**: the authenticated response shape cannot be observed
without credentials, and the prefix may not appear there. But a parser that depends on a
fixed byte offset is fragile regardless — see `ntu_fetch.py`, which anchors on the first
`{` or `[` instead.

## Ceiba positional parsing

```python
rows[0].find("td").string   # title
rows[1].find("td").string   # date
rows[5].find("td")          # content
```

Hard table indices. Any added or removed row silently mis-assigns fields — a title landing
in the body, or an exception from a vanished row. Untested. If Ceiba is needed, verify
against a live page before trusting the output.

## Credential shape

`config.yaml`, plaintext:

```yaml
ntu_user: "bXXXXXXXX"   # 學號格式
ntu_pass: "123456789"
telegram_bot_token: "..."
telegram_chat_id: "..."
```

`.gitignore` does cover `config.yaml`, so the file is not committed — but the secret sits on
disk in the working tree for the life of the deployment. `scripts/ntu_fetch.py` takes
credentials from the environment or a `--cred-file` path instead, so nothing needs to be
written into a repo at all.

## Verdict

Adopt the *approach* — content-hash dedupe, `present` soft delete, raw-first output — and
reimplement the fetch in ~50 lines. Do not adopt the service. Its unique value is the SAML
login sequence, and everything else (scheduling, storage, delivery, web UI) is already
solved on this machine by cron + SQLite + the digest pipeline.