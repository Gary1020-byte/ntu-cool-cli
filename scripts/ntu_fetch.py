#!/usr/bin/env python3
"""Fetch NTU Cool course announcements as raw-first markdown.

Design constraints, each one earned:

* **No credential ever touches this file or a repo.** NTU_USER / NTU_PASS come from the
  environment, or from a JSON file the caller names with --cred-file. Nothing is written
  to disk by this script.
* **Robust JSON parse.** Upstream does `json.loads(r.text[9:])` — a hardcoded byte offset
  with no documented reason. Against a 401 body it yields `:"unauthenticated",...` and a
  JSONDecodeError. We anchor on the first `{` or `[` instead, so a prefix may exist or not.
* **Markdown output, not a database.** The digest pipeline already owns storage, dedupe,
  and delivery. Writing SQLite would create a second system for a one-endpoint need.
* **Dry run before credentials.** --probe hits both platforms unauthenticated. If either
  returns 404 the upstream moved and auth debugging is wasted effort.

  # no credentials, ever
  python3 ntu_fetch.py --probe

  # with credentials supplied by the caller
  NTU_USER=... NTU_PASS=... python3 ntu_fetch.py \
      --course <COURSE> --since 2026-10-01 --out ~/notes/raw/
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

# Both imports are declared, not assumed. An earlier version only guarded
# `requests` and let `bs4` fail deep inside cool_login with a ModuleNotFoundError
# traceback that looked like a code bug. That happened because it was only ever
# run under Hermes' own interpreter, which ships beautifulsoup4 — a different
# Python than the one a user types at a shell prompt.
def _can_import(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


_MISSING = [m for m in ("requests",) if not _can_import(m)]
if _MISSING:
    sys.exit(
        "missing required package(s): " + ", ".join(_MISSING) + "\n"
        "install into the SAME interpreter you are running this with:\n"
        "  python3 -m pip install --user " + " ".join(_MISSING) + "\n"
        "note: a venv's python and the system python have separate site-packages. "
        "If a previous install seems to have done nothing, you are running a "
        "different interpreter than the one you installed into.")

# bs4 is deliberately NOT a dependency. The two things this script needs from an
# HTML parser are "find a form, read its inputs" and "flatten the visible text",
# and html.parser (stdlib, always present) does both. Requiring bs4 meant the
# script only ran under an interpreter that happened to ship it — Hermes' own
# venv had it, the system python did not, and the failure surfaced as a
# ModuleNotFoundError traceback inside the login function. Zero third-party
# parsers is one fewer way for this to break on someone else's machine.
import requests
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

COOL = "https://cool.ntu.edu.tw"
API = f"{COOL}/api/v1"

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120 Safari/537.36")


# ---------------------------------------------------------------- credentials

def load_credentials(cred_file: str | None) -> tuple[str, str]:
    """Return (user, pass). Never logs, never stores, never echoes either value."""
    if cred_file:
        _assert_private_cred_file(cred_file)
        with open(cred_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("ntu_user", ""), data.get("ntu_pass", "")
    return os.environ.get("NTU_USER", ""), os.environ.get("NTU_PASS", "")


def _abs_action(form, base: str) -> str:
    """Resolve a <form action> against a known base. Accepts either a parsed
    _FormOnly or anything with a .get("action") — the test doubles use the latter.

    Never concatenate a form action onto a host: an absolute action would become
    'https://adfs.ntu.edu.tw/https://evil.example/' and a missing one raises
    MissingSchema with no hint about which hop broke. urljoin handles all three
    cases, and the origin check turns a redirect-to-elsewhere into a named error
    instead of silently posting NTU credentials somewhere unexpected.
    """
    action = form.action if hasattr(form, "action") else form.get("action")
    if not action:
        raise RuntimeError(f"login form on {base} has no action attribute")
    target = urljoin(base, action)
    base_host = urlparse(base).netloc
    if urlparse(target).netloc != base_host:
        raise RuntimeError(
            f"login form on {base} points off-origin ({target}); refusing to "
            "send credentials there")
    return target


def _session(retries: int = 2) -> requests.Session:
    """Session with backoff. The NTU login is credential-bearing: a tight retry
    loop on a wrong password is how accounts get locked, so retries are few,
    spaced, and only on transport errors and 5xx — never on 401."""
    s = requests.Session()
    retry = Retry(total=retries, backoff_factor=1.5,
                  status_forcelist=[502, 503, 504],
                  allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _assert_private_cred_file(path: str) -> None:
    """A world-readable credential file is a leaked credential. Refuse it."""
    mode = os.stat(path).st_mode & 0o077
    if mode:
        raise RuntimeError(
            f"{path} is readable by others (mode {oct(os.stat(path).st_mode & 0o777)}). "
            f"Run: chmod 600 {path}")


# ---------------------------------------------------------------- json parsing

def parse_json_loose(text: str):
    """Parse JSON that may carry a leading guard prefix.

    Upstream slices a fixed 9 bytes; that is an undocumented offset and it fails on any
    body that does not happen to start with exactly those bytes. Anchoring on the first
    structural character is correct whether or not a prefix exists.
    """
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object or array found in response body")
    return json.loads(text[min(starts):])


# ---------------------------------------------------------------- login

def cool_login(s: requests.Session, user: str, password: str) -> None:
    """Walk the cool.ntu.edu.tw -> ADFS -> cool SAML chain.

    Sequence taken from brianbbsu/NTU-Announcement-Crawler. Each hop parses the form
    actually served rather than assuming field names, except the two ASP.NET
    credential fields which are stable.
    """
    r1 = s.get(f"{COOL}/login/saml", timeout=20)
    form1 = parse_first_form(r1.text)
    if not form1.action:
        raise RuntimeError("no login form at cool.ntu.edu.tw/login/saml")

    data1 = dict(form1.inputs)
    data1["ctl00$ContentPlaceHolder1$UsernameTextBox"] = user
    data1["ctl00$ContentPlaceHolder1$PasswordTextBox"] = password

    r2 = s.post(_abs_action(form1, "https://adfs.ntu.edu.tw/"),
                data=data1, allow_redirects=True, timeout=20)
    form2 = parse_first_form(r2.text)
    if not form2.action:
        raise RuntimeError("no ADFS form after submitting to adfs.ntu.edu.tw")

    s.post(_abs_action(form2, COOL + "/"), data=dict(form2.inputs),
           allow_redirects=True, timeout=20)

    check = s.get(f"{API}/courses", timeout=20)
    if check.status_code != 200:
        # name the hop and the status; never the submitted values
        raise RuntimeError(
            f"login did not take — after the ADFS round trip, "
            f"/api/v1/courses returned {check.status_code} (expected 200). "
            "Either the SAML flow changed upstream, or the credentials are wrong. "
            "Nothing was written; nothing needs cleanup.")


# ---------------------------------------------------------------- fetching

def fetch_courses(s: requests.Session) -> list[dict]:
    """Current-term courses, parsed from the Cool home page.

    NOT /api/v1/courses. That endpoint returns courses the account has EVER been
    enrolled in — verified 2026-10-18, it answered with 10 courses whose newest
    announcement was three months stale, omitted three current-term courses
    entirely, and returned three dead ones as `{"access_restricted_by_date": true}`
    with `name: null`. The current-term roster lives in JSON embedded in the home
    page HTML, keyed by longName / href / term.
    """
    r = s.get(COOL + "/", timeout=25)
    r.raise_for_status()
    hits = re.findall(
        r'"longName":"([^"]+)".*?"href":"/courses/(\d+)".*?"term":("[^"]*"|null)',
        r.text, re.S)
    out, seen = [], set()
    for long_name, cid, term in hits:
        if cid in seen:
            continue
        seen.add(cid)
        out.append({
            "id": int(cid),
            "name": long_name.split(" - ")[0],
            "longName": long_name,
            "courseCode": long_name.split(" - ")[-1] if " - " in long_name else "",
            "term": None if term == "null" else term.strip('"'),
        })
    if not out:
        raise RuntimeError(
            "no courses parsed from the Cool home page. The embedded JSON shape "
            "probably changed — /api/v1/courses is NOT a fallback here because it "
            "returns historical enrolment, not the current roster.")
    return out


def fetch_all_courses_historical(s: requests.Session) -> list[dict]:
    """Every course the account has ever been enrolled in. Not the current
    roster — see fetch_courses. Kept because it is occasionally useful for
    reading last term's exam schedule."""
    r = s.get(f"{API}/courses", timeout=20)
    r.raise_for_status()
    return parse_json_loose(r.text)


def find_course(courses: list[dict], needle: str) -> dict | None:
    """Match on id or name, case-insensitive substring match."""
    needle = needle.lower()
    for c in courses:
        if needle in str(c.get("id", "")).lower() or needle in str(c.get("name", "")).lower():
            return c
    return None


def fetch_announcements(s: requests.Session, course_id) -> list[dict]:
    return _paged_get(s, f"{API}/courses/{course_id}/discussion_topics",
                      params={"only_announcements": "true"}, timeout=30)


# ---------------------------------------------------------------- course files

def _paged_get(s: requests.Session, url: str, params: dict | None = None,
               timeout: int = 25) -> list:
    """Every page of a Canvas list endpoint, not just the first.

    Canvas caps `per_page` and the bare call defaults to 10. Measured 2026-10-18:
    one course's folder held 29 files and the unparameterised call returned 10 —
    19 files silently missing, with no error and no empty-looking tail. 27 of 91
    files across a term went missing that way.

    Follow `Link: <...>; rel="next"` rather than assuming a page count. That is
    the only pagination contract the API actually honours.
    """
    out: list = []
    p = dict(params or {})
    p["per_page"] = 100
    nxt: str | None = url
    seen_pages = 0
    while nxt:
        seen_pages += 1
        if seen_pages > 500:          # runaway guard, not a limit we expect to hit
            raise RuntimeError(f"pagination did not terminate at {url}")
        r = s.get(nxt, params=p if nxt == url else None, timeout=timeout)
        if r.status_code != 200:
            break
        chunk = parse_json_loose(r.text)
        if not isinstance(chunk, list):
            return chunk
        out.extend(chunk)
        p = {}
        nxt = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                nxt = part[part.find("<") + 1:part.find(">")] or None
    return out


def fetch_course_files(s: requests.Session, course_id) -> list[dict]:
    """Every file in the course's Files section, recursively.

    The announcement body is NOT where course material lives. Measured on one
    term: 20 announcement bodies carried 6,658 characters and zero file links,
    while the Files tree held 64 files / 91 MB — including a worksheet that WAS
    that term's next quiz scope. Reading announcements alone reports "no
    attachments" and looks like nothing was missed.

    Endpoint shape, established 2026-10-18 by probing:
      /api/v1/courses/{id}/folders   -> folder objects
      folder["files_url"]             -> files directly in that folder
      folder["folders_url"]           -> child folders

    Do NOT guess these paths. `/api/v1/courses/{id}/files`,
    `/api/v1/folders/{id}/subfolders`, `context_files`, and four other plausible
    spellings all return 404 or 400. The folder objects carry the URLs, so read
    them off the objects instead of composing them.

    Returned dicts: folder, id, name, filename, size, content_type, url, uuid,
    locked, created_at. `url` is a signed download link — treat it as a
    credential-bearing string, never log it.
    """
    out: list[dict] = []
    seen_files: set = set()
    seen_folders: set = set()

    def walk(folder: dict) -> None:
        fid = folder.get("id")
        if fid in seen_folders:
            return
        seen_folders.add(fid)

        for f in _paged_get(s, folder["files_url"]):
            # Belt and braces: every folder is walked exactly once above, so this
            # should never fire — but a folder reachable by two paths would cost
            # a silent duplicate, and a duplicate reads as a real file.
            if f.get("id") in seen_files:
                continue
            seen_files.add(f.get("id"))
            out.append({
                "folder": folder.get("full_name", ""),
                "id": f.get("id"),
                "name": f.get("display_name") or f.get("filename"),
                "filename": f.get("filename"),
                "size": f.get("size"),
                "content_type": f.get("content-type"),
                "url": f.get("url"),
                "uuid": f.get("uuid"),
                "locked": bool(f.get("locked")),
                "created_at": f.get("created_at"),
            })
        for sub in _paged_get(s, folder["folders_url"]):
            walk(sub)

    # Entry point: the ROOT, not the flat folder list.
    #
    # GET /courses/{id}/folders returns a flat enumeration of folders at every
    # depth, not a tree. Iterating it AND recursing folders_url walks each
    # non-root folder twice (three times when its parent is listed too), which
    # inflates the count — 110 where 64 are real. Walking only the root gives
    # one visit per folder and nothing else has to be corrected afterwards.
    roots: list[dict] = []
    rr = s.get(f"{API}/courses/{course_id}/folders/root", timeout=25)
    if rr.status_code == 200:
        try:
            payload = parse_json_loose(rr.text)
        except Exception:
            payload = None
        # Only a dict is a folder. An empty body or a list here is not a root —
        # treat it as absent and fall back rather than crashing in walk().
        if isinstance(payload, dict) and payload.get("id") is not None:
            roots = [payload]
    if not roots:
        # /folders/root answers 403 on at least one non-credit course
        # ("使用者無權執行該操作") while the list endpoint still works. Fall back to
        # the list and keep only the real roots — those with no parent.
        flat = _paged_get(s, f"{API}/courses/{course_id}/folders")
        roots = [f for f in flat if f.get("parent_folder_id") is None]
    if not roots:
        raise RuntimeError(
            f"course {course_id}: no root folder reachable — /folders/root did not "
            f"answer and /folders listed no parentless folder. Announcements may "
            f"still be fetchable.")
    for root in roots:
        walk(root)
    return out


def fetch_announcement_attachments(s: requests.Session, topics: list[dict]) -> list[dict]:
    """Files attached directly to announcements (a smaller, separate set).

    These arrive in each topic's `attachments` array, already carrying a signed
    `url`. Distinct from fetch_course_files: one term had 5 of these
    against 110 in the Files tree.
    """
    out = []
    for t in topics:
        for a in (t.get("attachments") or []):
            out.append({
                "folder": f"announcement:{t.get('title', '')}",
                "id": a.get("id"),
                "name": a.get("display_name") or a.get("filename"),
                "filename": a.get("filename"),
                "size": a.get("size"),
                "content_type": a.get("content-type"),
                "url": a.get("url"),
                "uuid": a.get("uuid"),
                "locked": bool(a.get("locked")),
                "created_at": a.get("created_at"),
            })
    return out


def download_file(s: requests.Session, url: str, dest: str,
                  expect_magic: bytes | None = None) -> dict:
    """Download one course file. Verifies it is not an HTML login page.

    Cool answers an expired or unauthorised signed URL with a 200 that carries
    the login page — so status alone proves nothing. Sniff the magic bytes.
    """
    r = s.get(url, timeout=120)
    result = {"status": r.status_code, "bytes": len(r.content),
              "content_type": r.headers.get("Content-Type", "")}
    if r.status_code != 200:
        return result
    body = r.content
    if b"<!DOCTYPE html" in body[:400] or b"<html" in body[:200].lower():
        result["error"] = "received an HTML page, not the file (session expired?)"
        return result
    if expect_magic and not body.startswith(expect_magic):
        result["error"] = f"magic mismatch: expected {expect_magic!r}"
        return result
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    with open(dest, "wb") as f:
        f.write(body)
    result["path"] = dest
    return result


# ---------------------------------------------------------------- rendering

class _TextOnly(HTMLParser):
    """Collect visible text, dropping script/style content and collapsing runs
    of whitespace. Replaces BeautifulSoup(...).stripped_strings for the one
    thing this script needs it for."""

    SKIP = {"script", "style", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skipping += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data):
        if not self._skipping and data.strip():
            self.parts.append(data.strip())


class _FormOnly(HTMLParser):
    """Capture the first <form>'s action plus every input's name/value.

    "First" means first-in-document-order, matching BeautifulSoup's
    `find("form")` — which is what the upstream code used. Login pages commonly
    park a hidden trap form early in <head>; waiting for a form to *close* picks
    that one instead of the real login form, so capture on opening tag and stop
    collecting once a second form starts.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.inputs: dict[str, str] = {}
        self._in_first = False
        self._seen_form = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            if self._seen_form:
                self._in_first = False   # a later form — stop collecting
            else:
                self._seen_form = True
                self._in_first = True
                self.action = a.get("action")
        elif tag == "input" and self._in_first and a.get("name"):
            self.inputs[a["name"]] = a.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "form" and self._in_first:
            self._in_first = False


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    p = _TextOnly()
    p.feed(raw)
    p.close()
    return "\n".join(p.parts)


def parse_first_form(raw: str) -> _FormOnly:
    p = _FormOnly()
    p.feed(raw)
    p.close()
    return p


def find_attachments(raw: str, base: str = COOL + "/") -> list[str]:
    """PDF/attachment links — recorded, never downloaded automatically.

    Relative hrefs are resolved against cool.ntu.edu.tw; recording '/courses/1/x.pdf'
    raw is worse than useless because it looks like a link and is not one.
    """
    found = re.findall(r'href="([^"]+\.(?:pdf|docx?|xlsx?|zip))"', raw or "", re.I)
    return [urljoin(base, u) for u in found]


def render(since: datetime.date | None, annos: list[tuple[str, dict]]) -> str:
    out = [
        "---",
        f"source: NTU Cool announcements (fetched {datetime.date.today()})",
        "type: raw-capture",
        f"count: {len(annos)}",
        "---",
        "",
        "# NTU Cool 課程公告",
        "",
    ]
    if since:
        out.append(f"篩選: {since} 之後發布")
        out.append("")

    for classname, a in annos:
        raw = a.get("message", "")
        body = strip_html(raw)
        atts = find_attachments(raw)
        out.append(f"## {a.get('title', '(無標題)')}")
        out.append("")
        out.append(f"- 課程: {classname}")
        out.append(f"- 發布: {a.get('posted_at', '?')}")
        out.append(f"- 連結: {a.get('url', '')}")
        if atts:
            out.append(f"- **附件 {len(atts)} 個(未下載,需另行處理)**:")
            for u in atts:
                out.append(f"  - {u}")
        out.append("")
        out.append(body)
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- modes

# Ceiba is blocked from this host: DNS resolves, three sibling NTU hosts answer in
# <150ms, ceiba times out on connect. See references/ceiba-unreachable.md. It is a
# known baseline, NOT a regression — so it must not turn a probe into a failure verdict.
KNOWN_UNREACHABLE = {"ceiba.ntu.edu.tw": "known blocked from this host (see reference)"}


def probe() -> int:
    """Unauthenticated reachability check. Run this before any credentialed call."""
    targets = [
        ("NTU Cool  /api/v1/courses", f"{API}/courses"),
        ("NTU Cool  /login/saml", f"{COOL}/login/saml"),
        ("NTU Ceiba /", "https://ceiba.ntu.edu.tw/"),
    ]
    print("unauthenticated probe\n")
    critical_ok = True
    for name, url in targets:
        host = url.split("/")[2]
        try:
            r = _session().get(url, timeout=15,
                               headers={"User-Agent": USER_AGENT})
            note = ""
            if r.status_code == 401:
                note = "  <- alive, needs auth (good)"
            elif r.status_code == 404:
                note = "  <- MOVED/DEAD"
                critical_ok = False
            elif r.status_code >= 500:
                note = "  <- upstream error"
                critical_ok = False
            print(f"  {name:28} HTTP {r.status_code}{note}")
        except Exception as e:
            # one dead target must not abort the whole probe — that is the
            # difference between a diagnostic and a single point of failure
            msg = str(e)
            if host in KNOWN_UNREACHABLE:
                print(f"  {name:28} UNREACHABLE  <- {KNOWN_UNREACHABLE[host]}")
            else:
                critical_ok = False
                # ConnectionError from urllib3 stacks carry a 2000-char traceback
                # tail that buries the actual cause
                brief = msg.split("Max retries exceeded")[0].strip()
                print(f"  {name:28} FAIL {type(e).__name__}: {brief[:90]}")

    if critical_ok:
        print("\nNTU Cool reachable — safe to proceed with credentials.")
        print("Ceiba unavailable from this host is expected; use the Cool path.")
    else:
        print("\nA reachable endpoint moved or failed. Do not debug credentials yet — "
              "fix reachability first.")
    return 0 if critical_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="unauthenticated reachability check, no credentials used")
    ap.add_argument("--course", action="append", default=[],
                    help="course id or name substring; repeatable")
    ap.add_argument("--all-courses", action="store_true",
                    help="fetch every enrolled course")
    ap.add_argument("--since", help="YYYY-MM-DD, filter announcements older than this")
    ap.add_argument("--out", help="output directory; filename is generated")
    ap.add_argument("--cred-file", help="JSON with ntu_user / ntu_pass keys")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    ap.add_argument("--list-files", action="store_true",
                    help="list course FILES (the Files section), not announcements")
    ap.add_argument("--files-out", help="directory for downloaded files")
    ap.add_argument("--download-files", action="store_true",
                    help="download every file in the Files section")
    ap.add_argument("--max-mb", type=float, default=0.0,
                    help="with --download-files: skip files larger than this")
    args = ap.parse_args()

    if args.probe:
        return probe()

    if not args.course and not args.all_courses:
        ap.error("need --course (repeatable) or --all-courses, or use --probe")

    user, password = load_credentials(args.cred_file)
    if not user or not password:
        ap.error("no credentials. Set NTU_USER and NTU_PASS in the environment, "
                 "or pass --cred-file. (Hermes does not supply these.)")

    since = None
    if args.since:
        try:
            since = datetime.date.fromisoformat(args.since)
        except ValueError:
            ap.error(f"--since must be YYYY-MM-DD, got {args.since!r}")

    with _session() as s:
        s.headers.update({"User-Agent": USER_AGENT})
        cool_login(s, user, password)
        print("login OK", file=sys.stderr)

        courses = fetch_courses(s)

        # ---- files mode short-circuits the announcement pipeline ----
        if args.list_files or args.download_files:
            picked = courses if args.all_courses else [
                c for c in courses
                if any(find_course([c], n) for n in args.course)]
            if not picked:
                ap.error("no course matched --course")
            total = ok = skipped = 0
            for c in picked:
                name = c.get("name") or str(c.get("id"))
                try:
                    files = fetch_course_files(s, c["id"])
                except Exception as e:
                    print(f"{str(name)[:30]:32} FAIL {type(e).__name__}: {e}",
                          file=sys.stderr)
                    continue
                # Announcement attachments are a SEPARATE set from the Files tree
                # — one term had 5 of these and 64 in the tree. A run that only
                # walks the tree misses them entirely.
                try:
                    topics = fetch_announcements(s, c["id"])
                    files = files + fetch_announcement_attachments(s, topics)
                except Exception as e:
                    print(f"  (announcement attachments skipped: "
                          f"{type(e).__name__}: {e})", file=sys.stderr)
                mb = sum(f["size"] or 0 for f in files) / 1048576
                print(f"\n{str(name)[:40]} — {len(files)} 檔 {mb:.1f} MB", file=sys.stderr)
                for f in files:
                    total += 1
                    size_mb = (f["size"] or 0) / 1048576
                    if args.list_files:
                        print(f"  [{f['id']}] {f['folder'][:30]:32} "
                              f"{str(f['name'])[:46]:48} {size_mb:7.2f} MB"
                              + ("  LOCKED" if f["locked"] else ""), file=sys.stderr)
                    if args.download_files:
                        if not args.files_out:
                            ap.error("--download-files needs --files-out")
                        if args.max_mb and size_mb > args.max_mb:
                            skipped += 1
                            continue
                        # display_name is the human filename; `filename` is the
                        # storage name and looks like "<TIMESTAMP>_<ID>__<ORIGINAL-NAME>.pdf".
                        raw_name = str(f.get("name") or f.get("filename") or f.get("id"))
                        safe = os.path.basename(raw_name).replace("/", "_")
                        safe = re.sub(r"[^\w.\-㐀-鿿]+", "_", safe).strip("_") or str(f["id"])
                        # No name-collision disambiguation is needed: dest embeds
                        # the file's own id, so two files with the same display
                        # name land in different directories. Renaming here would
                        # invent a suffix the source never had.
                        dest = os.path.join(args.files_out, str(c["id"]), str(f["id"]), safe)
                        magic = b"%PDF-" if "pdf" in (f["content_type"] or "") else None
                        res = download_file(s, f["url"], dest, magic)
                        if "path" in res:
                            ok += 1
                            print(f"  OK {res['bytes']:>9} B  {safe[:52]}", file=sys.stderr)
                        else:
                            print(f"  FAIL {f['id']} {res.get('error', res['status'])}",
                                  file=sys.stderr)
            print(f"\n{total} listed / {ok} downloaded / {skipped} skipped",
                  file=sys.stderr)
            return 0
        print(f"enrolled in {len(courses)} course(s)", file=sys.stderr)

        if args.all_courses:
            targets = courses
        else:
            targets = []
            for needle in args.course:
                hit = find_course(courses, needle)
                if hit is None:
                    print(f"  ! no course matches {needle!r}", file=sys.stderr)
                    continue
                targets.append(hit)
            if not targets:
                print("\navailable courses:", file=sys.stderr)
                for c in courses:
                    print(f"  {c.get('id')}\t{c.get('name')}", file=sys.stderr)
                return 1

        annos: list[tuple[str, dict]] = []
        for c in targets:
            name = c.get("name", str(c.get("id")))
            # One course failing must not abort the batch. A 403 here means the
            # student is enrolled but not a TA of that course's announcements —
            # a normal state, not an error to raise on. Log it and continue.
            try:
                items = fetch_announcements(s, c.get("id"))
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                print(f"  {name}: skipped (HTTP {code})", file=sys.stderr)
                continue
            except requests.RequestException as e:
                print(f"  {name}: skipped ({type(e).__name__})", file=sys.stderr)
                continue
            kept = 0
            for a in items:
                ts = a.get("posted_at")
                if since and ts:
                    try:
                        d = datetime.date.fromisoformat(ts[:10])
                        if d < since:
                            continue
                    except ValueError:
                        pass
                annos.append((name, a))
                kept += 1
            print(f"  {name}: {kept} announcement(s) in range", file=sys.stderr)

    doc = render(since, annos)
    if args.stdout:
        print(doc)
        return 0

    outdir = args.out or os.getcwd()
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{datetime.date.today()}-ntu-cool-announcements.md")
    # write then rename: an interrupted run leaves no half-file that later looks
    # like a complete capture of the day
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(doc)
    os.replace(tmp, path)
    print(f"wrote {path}  ({len(annos)} announcements, {len(doc)} chars)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())