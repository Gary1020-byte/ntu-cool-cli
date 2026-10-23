"""Offline tests for ntu_fetch. No network, no credentials, no login.

Run:  python3 -m unittest discover -s tests -v
     or: python3 tests/test_ntu_fetch.py

These cover the parts that broke repeatedly while building the tool: the JSON
prefix handling, form extraction without BeautifulSoup, and the credential-file
permission guard. Everything here runs in milliseconds and can never touch
cool.ntu.edu.tw.
"""

import json
import os
import stat
import sys
import tempfile
import inspect
import pathlib
import re
import subprocess
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ntu_fetch  # noqa: E402


class TestParseJsonLoose(unittest.TestCase):
    """A fixed-offset `json.loads(r.text[9:])` has no documented reason for 9.
    Our parser anchors on the first `{` or `[`, so a prefix may exist or not."""

    def test_bare_object(self):
        self.assertEqual(ntu_fetch.parse_json_loose('{"a": 1}'), {"a": 1})

    def test_bare_array(self):
        self.assertEqual(ntu_fetch.parse_json_loose('[1, 2]'), [1, 2])

    def test_prefix_before_object(self):
        self.assertEqual(ntu_fetch.parse_json_loose('while(1);{"a": 1}'), {"a": 1})

    def test_prefix_of_length_nine(self):
        # The exact case a fixed slice handles and nothing else does.
        self.assertEqual(ntu_fetch.parse_json_loose('someprexx{"a": 1}'), {"a": 1})

    def test_auth_failure_body(self):
        body = '{"status":"unauthenticated","errors":[{"message":"需要使用者授權"}]}'
        self.assertEqual(ntu_fetch.parse_json_loose(body)["status"], "unauthenticated")

    def test_garbage_raises(self):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            ntu_fetch.parse_json_loose("not json at all")

    def test_empty_raises(self):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            ntu_fetch.parse_json_loose("")

    def test_round_trip_nested(self):
        obj = {"courses": [{"id": 1, "name": "x", "term": None}]}
        self.assertEqual(ntu_fetch.parse_json_loose(")]}'\n" + json.dumps(obj)), obj)


class TestStripHtml(unittest.TestCase):
    """The two things BeautifulSoup was used for: flatten visible text,
    and find a form and read its inputs."""

    def test_flattens_paragraphs(self):
        self.assertIn("截止 10/20", ntu_fetch.strip_html("<p>截止 10/20 23:59</p>"))

    def test_drops_script_and_style(self):
        out = ntu_fetch.strip_html("<p>keep</p><script>var x=1;</script><style>p{}</style>")
        self.assertIn("keep", out)
        self.assertNotIn("var x", out)
        self.assertNotIn("p{}", out)

    def test_unescapes_entities(self):
        self.assertIn("a & b", ntu_fetch.strip_html("<p>a &amp; b</p>"))

    def test_empty_returns_empty(self):
        self.assertEqual(ntu_fetch.strip_html("").strip(), "")


class TestParseFirstForm(unittest.TestCase):
    """parse_first_form returns the FIRST form in document order.

    That is deliberate and it is NOT the security boundary — a login page can
    park a trap form early in <head>, and this function will hand it back. The
    credential protection lives in _abs_action, tested separately below. Do not
    'fix' this by making parse_first_form pick a form: it has no idea what the
    legitimate origin is."""

    FORM = """
    <html><head><form action="https://evil.example/steal" method="post">
      <input name="username" value="trap"></form></head>
    <body><form action="/login/saml" method="post">
      <input name="username" value=""><input name="password" value="">
    </form></body></html>"""

    def test_returns_a_form(self):
        self.assertIsNotNone(ntu_fetch.parse_first_form(self.FORM))

    def test_it_picks_first_in_document_order(self):
        # Documenting current behaviour, including that it can be the decoy.
        form = ntu_fetch.parse_first_form(self.FORM)
        self.assertEqual(form.action, "https://evil.example/steal")

    def test_no_form_yields_empty_object_not_an_error(self):
        # The caller raises on a missing action, not this parser.
        form = ntu_fetch.parse_first_form("<html><body>no form here</body></html>")
        self.assertIsNone(form.action)
        self.assertEqual(form.inputs, {})

    def test_collects_inputs_of_the_first_form_only(self):
        form = ntu_fetch.parse_first_form(self.FORM)
        self.assertEqual(form.inputs, {"username": "trap"})


class TestCredentialFilePermissions(unittest.TestCase):
    """A group- or world-readable credential file must be refused."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "creds.json")
        with open(self.path, "w") as f:
            f.write(json.dumps({"ntu_user": "x", "ntu_pass": "x"}))

    def tearDown(self):
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        os.remove(self.path)
        os.rmdir(self.dir)

    def test_private_file_accepted(self):
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)  # 600
        # Should not raise.
        ntu_fetch._assert_private_cred_file(self.path)

    def test_group_readable_refused(self):
        os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)  # 640
        with self.assertRaises(Exception):
            ntu_fetch._assert_private_cred_file(self.path)

    def test_world_readable_refused(self):
        os.chmod(self.path, 0o644)
        with self.assertRaises(Exception):
            ntu_fetch._assert_private_cred_file(self.path)


class TestFindCourse(unittest.TestCase):
    COURSES = [
        {"id": 1, "name": "Course Alpha"},
        {"id": 2, "name": "Course Beta"},
        {"id": 3, "name": None},
    ]

    def test_match_by_id(self):
        self.assertEqual(ntu_fetch.find_course(self.COURSES, "2")["id"], 2)

    def test_match_by_name_substring(self):
        self.assertEqual(ntu_fetch.find_course(self.COURSES, "beta")["id"], 2)

    def test_case_insensitive(self):
        self.assertEqual(ntu_fetch.find_course(self.COURSES, "ALPHA")["id"], 1)

    def test_no_match_returns_none(self):
        self.assertIsNone(ntu_fetch.find_course(self.COURSES, "nonexistent"))


class TestNoWriteMethods(unittest.TestCase):
    """Read-only is a contract, not a convention. If a POST/PUT/PATCH/DELETE
    ever lands in the fetch layer, this test fails loudly."""

    def test_fetch_layer_has_no_write_verbs(self):
        import re

        with open(ntu_fetch.__file__ or "", encoding="utf-8") as fh:
            src = fh.read()
        # Everything after the login function is the fetch layer.
        fetch_layer = src.split("def fetch_courses", 1)[1]
        offenders = re.findall(r"\.(post|put|patch|delete|request)\(", fetch_layer)
        self.assertEqual(
            offenders,
            [],
            f"write verbs in fetch layer: {offenders}",
        )




class TestAbsActionRefusesOffOrigin(unittest.TestCase):
    """THE credential safety boundary.

    A trap form in <head> is picked up by parse_first_form. It must never
    become a POST target. _abs_action resolves the action against the hop's own
    base and rejects a different origin, so the worst case is a named error —
    not a credential sent somewhere unexpected."""

    BASE = "https://adfs.ntu.edu.tw/"

    def _form(self, action):
        class F:
            pass
        f = F()
        f.action = action
        f.inputs = {}
        return f

    def test_off_origin_action_is_refused(self):
        with self.assertRaises(Exception) as ctx:
            ntu_fetch._abs_action(self._form("https://evil.example/steal"), self.BASE)
        self.assertIn("off-origin", str(ctx.exception))

    def test_protocol_relative_off_origin_is_refused(self):
        with self.assertRaises(Exception):
            ntu_fetch._abs_action(self._form("//evil.example/x"), self.BASE)

    def test_lookalike_host_is_refused(self):
        with self.assertRaises(Exception):
            ntu_fetch._abs_action(self._form("https://adfs.ntu.edu.tw.evil.example/x"),
                                 self.BASE)

    def test_same_origin_relative_is_accepted(self):
        self.assertEqual(
            ntu_fetch._abs_action(self._form("/auth"), self.BASE),
            "https://adfs.ntu.edu.tw/auth",
        )

    def test_same_origin_absolute_is_accepted(self):
        self.assertEqual(
            ntu_fetch._abs_action(self._form("https://adfs.ntu.edu.tw/auth"), self.BASE),
            "https://adfs.ntu.edu.tw/auth",
        )

    def test_missing_action_is_a_hard_error(self):
        with self.assertRaises(Exception):
            ntu_fetch._abs_action(self._form(None), self.BASE)

    def test_full_trap_path_cannot_post_off_origin(self):
        """End to end through the real parser: trap form in <head>, real form
        in <body>. The parser hands back the trap; the guard must stop it."""
        page = (
            '<html><head><form action="https://evil.example/steal" method="post">'
            '<input name="username"></form></head>'
            '<body><form action="/auth" method="post"><input name="password"></form>'
            '</body></html>'
        )
        form = ntu_fetch.parse_first_form(page)
        self.assertEqual(form.action, "https://evil.example/steal")  # trap is first
        with self.assertRaises(Exception) as ctx:
            ntu_fetch._abs_action(form, self.BASE)
        self.assertIn("off-origin", str(ctx.exception))


class _FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.status_code = status
        self.text = json.dumps(payload)
        self.content = self.text.encode()
        # _paged_get reads Link to find rel="next"; no Link means one page.
        self.headers = headers if headers is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Stands in for requests.Session. Every URL maps to canned payloads so the
    recursion can be driven without touching the network.

    The canned routes are keyed by the bare URL; the `per_page` param the code
    now sends is ignored on lookup, so a route describes what the endpoint holds
    in total, not one page of it. That is deliberate: these tests are about
    traversal and dedupe, and a separate class covers pagination."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        if url not in self.routes:
            return _FakeResponse([], status=404)
        return _FakeResponse(self.routes[url])


class TestFetchCourseFilesDedupes(unittest.TestCase):
    """THE bug this repo used to ship.

    /courses/{id}/folders returns the course root AND its subfolders in one
    response. A recursive walk therefore visits `unfiled` twice and every file
    in it twice. Measured on a real term: 110 files reported, 64 real. Any diff
    against local copies built on the uncorrected count is wrong in both
    directions. Dedupe by file id."""

    ROUTES = {
        "https://cool.ntu.edu.tw/api/v1/courses/1/folders": [
            {"id": 10, "full_name": "course files", "context_id": 1,
             "files_url": "https://x/files/root", "folders_url": "https://x/sub/root"},
            {"id": 11, "full_name": "course files/unfiled", "context_id": 1,
             "files_url": "https://x/files/unfiled", "folders_url": "https://x/sub/unfiled"},
        ],
        "https://x/files/root": [],
        "https://x/sub/root": [
            {"id": 11, "full_name": "course files/unfiled", "context_id": 1,
             "files_url": "https://x/files/unfiled", "folders_url": "https://x/sub/unfiled"},
        ],
        "https://x/files/unfiled": [
            {"id": 101, "display_name": "a.pdf", "filename": "1_a.pdf", "size": 10,
             "content-type": "application/pdf", "url": "https://x/d/101", "uuid": "u1",
             "locked": False, "created_at": "2026-01-01"},
            {"id": 102, "display_name": "b.pdf", "filename": "2_b.pdf", "size": 20,
             "content-type": "application/pdf", "url": "https://x/d/102", "uuid": "u2",
             "locked": False, "created_at": "2026-01-01"},
        ],
        "https://x/sub/unfiled": [],
    }

    def test_same_file_returned_twice_is_returned_once(self):
        s = _FakeSession(self.ROUTES)
        out = ntu_fetch.fetch_course_files(s, 1)
        ids = [f["id"] for f in out]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate ids leaked: {ids}")

    def test_expected_files_present(self):
        s = _FakeSession(self.ROUTES)
        out = ntu_fetch.fetch_course_files(s, 1)
        self.assertEqual(sorted(f["id"] for f in out), [101, 102])

    def test_count_is_not_inflated(self):
        s = _FakeSession(self.ROUTES)
        out = ntu_fetch.fetch_course_files(s, 1)
        self.assertEqual(len(out), 2, "the naive walk would report 4 here")

    def test_folder_name_is_preserved(self):
        s = _FakeSession(self.ROUTES)
        out = ntu_fetch.fetch_course_files(s, 1)
        self.assertTrue(all(f["folder"] == "course files/unfiled" for f in out))

    def test_display_name_beats_storage_filename(self):
        s = _FakeSession(self.ROUTES)
        out = ntu_fetch.fetch_course_files(s, 1)
        by_id = {f["id"]: f for f in out}
        self.assertEqual(by_id[101]["name"], "a.pdf")
        self.assertEqual(by_id[101]["filename"], "1_a.pdf")


class TestFetchAnnouncementAttachments(unittest.TestCase):
    """Announcement attachments are a SEPARATE set from the Files tree — one
    term had 5 of these and 64 in the tree. A run that only walks the tree
    misses them. This function must stay wired into the CLI."""

    def test_collects_the_attachments_array(self):
        topics = [{
            "title": "homework 1",
            "attachments": [
                {"id": 7, "display_name": "hw1.pdf", "filename": "1_hw1.pdf",
                 "size": 123, "content-type": "application/pdf",
                 "url": "https://x/d/7", "uuid": "u7", "locked": False},
            ],
        }]
        s = _FakeSession({})
        out = ntu_fetch.fetch_announcement_attachments(s, topics)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 7)
        self.assertEqual(out[0]["name"], "hw1.pdf")

    def test_no_attachments_yields_empty(self):
        self.assertEqual(
            ntu_fetch.fetch_announcement_attachments(_FakeSession({}),
                                                    [{"title": "t", "attachments": []}]),
            [])

    def test_missing_attachments_key_is_not_a_crash(self):
        self.assertEqual(
            ntu_fetch.fetch_announcement_attachments(_FakeSession({}), [{"title": "t"}]),
            [])

    def test_attachments_are_labeled_as_such(self):
        out = ntu_fetch.fetch_announcement_attachments(
            _FakeSession({}), [{"title": "notice", "attachments": [
                {"id": 1, "display_name": "x.pdf", "url": "https://x/1"}]}])
        self.assertTrue(out[0]["folder"].startswith("announcement:"))


class TestNoPersonalCourseRoster(unittest.TestCase):
    """The repo documented its traps using one account's real roster. That is
    a leak and it is not needed to make the point.

    The guard is written as a *pattern* check, never as a list of the real
    course names and codes: such a list would itself be the leak, living in
    this file. A pattern catches any course id or ESOE code, including ones
    added after this test was written.
    """

    # NTU course ids are five digits starting with 5 or 6; ESOE course codes
    # are ESOE followed by four digits.
    ID_RE = re.compile(r"(?<![0-9])[56][0-9]{4}(?![0-9])")
    CODE_RE = re.compile(r"ESOE[0-9]{4}")

    def _repo_files(self):
        """Files that would actually be published: the git-tracked set.

        Deliberately not a filesystem walk -- a stray capture file sitting in
        the working tree is personal material, not a publishable artifact, and
        failing the build on it would be noise rather than a real guard.
        """
        root = pathlib.Path(ntu_fetch.__file__).resolve().parent.parent
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "ls-files"],
                capture_output=True, text=True, check=True).stdout.split()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        return [root / p for p in out
                if pathlib.Path(p).suffix in {".md", ".py", ".toml", ".txt"}]

    def test_no_ntu_course_ids_anywhere(self):
        for path in self._repo_files():
            src = path.read_text(encoding="utf-8", errors="replace")
            hit = self.ID_RE.search(src)
            self.assertIsNone(
                hit, f"NTU course id {hit.group(0) if hit else ''!r} in {path}")

    def test_no_ese_course_codes_anywhere(self):
        for path in self._repo_files():
            src = path.read_text(encoding="utf-8", errors="replace")
            hit = self.CODE_RE.search(src)
            self.assertIsNone(
                hit, f"ESOE course code {hit.group(0) if hit else ''!r} in {path}")


class _PagedResponse(_FakeResponse):
    def __init__(self, payload, status=200, next_url=None):
        super().__init__(payload, status)
        if next_url:
            self.headers = {
                "Link": f'<{next_url}>; rel="next", <{next_url}>; rel="last"'}


class _PagedSession:
    """Returns one page per call and advertises the next through Link. This is
    the only pagination contract Canvas honours — there is no total count to
    compute a page count from."""

    def __init__(self, pages):
        self.pages = pages            # list of payloads, one per page
        self.calls = 0

    def get(self, url, params=None, **kw):
        idx = self.calls
        self.calls += 1
        if idx >= len(self.pages):
            return _FakeResponse([])
        nxt = f"https://x/page/{idx + 2}" if idx + 1 < len(self.pages) else None
        return _PagedResponse(self.pages[idx], next_url=nxt)


class TestPagedGet(unittest.TestCase):
    """THE bug that was silently losing files.

    Canvas defaults to per_page=10 and caps the parameter. One course's folder
    held 29 files and an unparameterised call returned 10 — 19 files gone, no
    error, no empty-looking tail. Across a term that was 27 of 91 files. The
    fix is to follow Link rel="next", not to guess a bigger page size."""

    def test_single_page_returns_everything(self):
        s = _PagedSession([[1, 2, 3]])
        self.assertEqual(ntu_fetch._paged_get(s, "https://x/all"), [1, 2, 3])
        self.assertEqual(s.calls, 1)

    def test_follows_next_across_pages(self):
        s = _PagedSession([[1, 2], [3, 4], [5]])
        self.assertEqual(ntu_fetch._paged_get(s, "https://x/all"), [1, 2, 3, 4, 5])

    def test_visits_each_page_once(self):
        s = _PagedSession([[1], [2], [3]])
        ntu_fetch._paged_get(s, "https://x/all")
        self.assertEqual(s.calls, 3)

    def test_no_link_header_means_one_page(self):
        s = _PagedSession([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]])
        out = ntu_fetch._paged_get(s, "https://x/all")
        self.assertEqual(len(out), 11, "must not truncate at 10")

    def test_non_list_payload_is_returned_whole(self):
        class S:
            def get(self, url, params=None, **kw):
                return _FakeResponse({"id": 1, "name": "root"})
        out = ntu_fetch._paged_get(S(), "https://x/root")
        self.assertEqual(out, {"id": 1, "name": "root"})

    def test_non_200_stops_and_returns_what_it_has(self):
        class S:
            def __init__(self): self.n = 0
            def get(self, url, params=None, **kw):
                self.n += 1
                if self.n == 1:
                    return _PagedResponse([1], next_url="https://x/p2")
                return _FakeResponse([], status=500)
        self.assertEqual(ntu_fetch._paged_get(S(), "https://x/all"), [1])

    def test_requests_a_page_size_above_the_canvas_default(self):
        seen = []

        class S:
            def get(self, url, params=None, **kw):
                seen.append(params)
                return _FakeResponse([])

        ntu_fetch._paged_get(S(), "https://x/all")
        self.assertTrue(seen and seen[0].get("per_page", 0) > 10,
                        f"default page size is still in play: {seen}")


class TestFetchCourseFilesEntersThroughTheRoot(unittest.TestCase):
    """Walking the flat /folders list AND recursing double-counts: that list
    enumerates folders at every depth, not just the root. 110 where 64 are real.
    The entry point must be the root, or the parentless entries of the list."""

    ROOT = {"id": 1, "full_name": "course files", "parent_folder_id": None,
            "files_url": "https://x/f/1", "folders_url": "https://x/d/1"}

    def test_root_endpoint_is_used_when_available(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders/root": self.ROOT,
            "https://x/f/1": [{"id": 11, "display_name": "a.pdf"}],
            "https://x/d/1": [],
        }
        s = _FakeSession(routes)
        out = ntu_fetch.fetch_course_files(s, 9)
        self.assertEqual([f["id"] for f in out], [11])

    class _403Root(_FakeSession):
        def get(self, url, **kw):
            if url.endswith("/folders/root"):
                return _FakeResponse({"status": "unauthorized"}, status=403)
            return super().get(url, **kw)

    class _NonDictRoot(_FakeSession):
        def get(self, url, **kw):
            if url.endswith("/folders/root"):
                return _FakeResponse([])      # 200, but not a folder
            return super().get(url, **kw)

    def test_falls_back_to_the_list_when_root_403s(self):
        # /folders/root answers 403 on at least one non-credit course while the
        # list endpoint still works. Losing that course entirely would be a
        # silent hole in the corpus.
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders/root": [],
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders": [
                self.ROOT,
                {"id": 2, "full_name": "course files/unfiled",
                 "parent_folder_id": 1,
                 "files_url": "https://x/f/2", "folders_url": "https://x/d/2"},
            ],
            "https://x/f/1": [],
            "https://x/d/1": [
                {"id": 2, "full_name": "course files/unfiled",
                 "parent_folder_id": 1,
                 "files_url": "https://x/f/2", "folders_url": "https://x/d/2"},
            ],
            "https://x/f/2": [{"id": 22, "display_name": "b.pdf"}],
            "https://x/d/2": [],
        }
        s = self._403Root(routes)
        out = ntu_fetch.fetch_course_files(s, 9)
        self.assertEqual([f["id"] for f in out], [22],
                         "fallback must enter only through the parentless folder")

    def test_falls_back_when_root_returns_a_non_dict(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders/root": [],
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders": [self.ROOT],
            "https://x/f/1": [{"id": 11, "display_name": "a.pdf"}],
            "https://x/d/1": [],
        }
        out = ntu_fetch.fetch_course_files(self._NonDictRoot(routes), 9)
        self.assertEqual([f["id"] for f in out], [11])

    def test_raises_when_no_root_is_findable(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders/root": [],
            "https://cool.ntu.edu.tw/api/v1/courses/9/folders": [],
        }
        with self.assertRaises(Exception):
            ntu_fetch.fetch_course_files(_FakeSession(routes), 9)


class TestFetchAssignments(unittest.TestCase):
    """`/assignments` is the homework roster. The syllabus is not."""

    def test_reads_the_assignments_endpoint(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/assignments": [
                {"id": 1, "name": "HW1", "due_at": "2026-10-22T15:59:59Z",
                 "lock_at": "2026-10-23T00:00:00Z", "points_possible": 100},
            ],
        }
        out = ntu_fetch.fetch_assignments(_FakeSession(routes), 9)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "HW1")
        self.assertEqual(out[0]["points_possible"], 100)

    def test_keeps_due_and_lock_separate(self):
        """`lock_at` is the real deadline; `due_at` is the nominal one.

        They are not the same value and not the same instant — the gap is the
        buffer the course page promises. Collapsing them loses that.
        """
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/assignments": [
                {"id": 1, "name": "HW1", "due_at": "2026-10-22T15:59:59Z",
                 "lock_at": "2026-10-23T00:00:00Z"},
            ],
        }
        a = ntu_fetch.fetch_assignments(_FakeSession(routes), 9)[0]
        self.assertNotEqual(a["due_at"], a["lock_at"])


class TestFetchOwnSubmission(unittest.TestCase):
    """`/submissions/self` returns 200; `/submissions?self=1` returns 403.

    Same session, same credentials — only the path differs. Using the list
    form makes every assignment look like a hard failure.
    """

    def test_uses_the_self_path(self):
        seen = []

        class S:
            def get(self, url, **kw):
                seen.append(url)
                return _FakeResponse({"workflow_state": "submitted",
                                       "submitted_at": "2026-10-20T10:00:00Z"})

        out = ntu_fetch.fetch_own_submission(S(), 9, 411106)
        self.assertEqual(out["workflow_state"], "submitted")
        self.assertTrue(seen[0].endswith("/assignments/411106/submissions/self"),
                        f"wrong path: {seen[0]}")
        self.assertNotIn("?self=1", seen[0])

    def test_missing_submission_is_none_not_an_exception(self):
        class S:
            def get(self, url, **kw):
                return _FakeResponse({}, status=404)

        self.assertIsNone(ntu_fetch.fetch_own_submission(S(), 9, 1))

    def test_workflow_state_is_readable(self):
        for state in ("unsubmitted", "submitted", "graded"):
            class S:
                def get(self, url, **kw):
                    return _FakeResponse({"workflow_state": state})

            self.assertEqual(
                ntu_fetch.fetch_own_submission(S(), 9, 1)["workflow_state"], state)


class TestFetchAssignmentHandouts(unittest.TestCase):
    """CA handouts live in the assignment description, not the Files tree.

    The link sits in a `data-api-endpoint` attribute whose href ends in
    `/download` — not a file extension — so the attachment grep misses it.
    """

    DESC = (
        '<p>see <a class="instructure_file_link" '
        'href="https://cool.ntu.edu.tw/courses/9/files/10140367/download" '
        'data-api-endpoint="https://cool.ntu.edu.tw/api/v1/courses/9/files/10140367" '
        'data-api-returntype="File">DS_CA3.zip</a></p>'
    )

    def test_finds_the_endpoint_in_the_description(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/assignments": [
                {"id": 411108, "name": "CA3", "description": self.DESC},
            ],
        }
        out = ntu_fetch.fetch_assignment_handouts(_FakeSession(routes), 9)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["assignment_id"], 411108)
        self.assertTrue(out[0]["endpoint"].endswith("/files/10140367"))

    def test_assignment_without_a_handout_yields_nothing(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/assignments": [
                {"id": 1, "name": "Reading", "description": "<p>no file here</p>"},
            ],
        }
        self.assertEqual(ntu_fetch.fetch_assignment_handouts(_FakeSession(routes), 9), [])

    def test_missing_description_is_handled(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/assignments": [
                {"id": 1, "name": "No description key at all"},
            ],
        }
        self.assertEqual(ntu_fetch.fetch_assignment_handouts(_FakeSession(routes), 9), [])


class TestFetchCoursePages(unittest.TestCase):
    """Pages are addressed by slug, and the slug is on the module item."""

    def test_collects_page_slugs_from_module_items(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/modules": [
                {"id": 5, "name": "Week 1", "items": [
                    {"type": "Page", "page_url": "ke-cheng-da-gang",
                     "title": "課程大綱", "url": "https://x/pages/ke-cheng-da-gang"},
                    {"type": "File", "title": "slide.pdf"},
                ]},
            ],
        }
        out = ntu_fetch.fetch_course_pages(_FakeSession(routes), 9)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["page_url"], "ke-cheng-da-gang")

    def test_course_with_no_modules_yields_no_pages(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/modules": [],
        }
        self.assertEqual(ntu_fetch.fetch_course_pages(_FakeSession(routes), 9), [])

    def test_asks_for_items_so_the_slugs_are_present(self):
        """Regression: reading the modules without `include[]=items` returns
        every `items` array empty, so the page list came back empty with no
        error at all. The page slugs only exist on the module items.
        """
        seen = []

        class S:
            def get(self, url, params=None, **kw):
                seen.append(params)
                return _FakeResponse([
                    {"id": 5, "name": "Week 1", "items": [
                        {"type": "Page", "page_url": "ke-cheng-da-gang",
                         "title": "課程大綱"},
                    ]},
                ])

        out = ntu_fetch.fetch_course_pages(S(), 9)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["page_url"], "ke-cheng-da-gang")
        self.assertTrue(seen and seen[0], "no params were sent")
        self.assertIn("include[]", seen[0],
                      f"include[] was not requested: {seen[0]}")


class TestFetchModules(unittest.TestCase):
    def test_returns_modules_with_their_items(self):
        routes = {
            "https://cool.ntu.edu.tw/api/v1/courses/9/modules": [
                {"id": 5, "name": "Week 1", "items": [{"type": "File"}]},
            ],
        }
        out = ntu_fetch.fetch_modules(_FakeSession(routes), 9)
        self.assertEqual(out[0]["name"], "Week 1")
        self.assertEqual(len(out[0]["items"]), 1)

    def test_asks_for_items_to_be_included(self):
        """Without `include[]=items` the API returns modules with empty
        `items` arrays — no error, just nothing. Measured against the live
        site: 8 modules, 0 items without it, 6 items in the first module
        with it.
        """
        seen = []

        class S:
            def get(self, url, params=None, **kw):
                seen.append(params)
                return _FakeResponse([{"id": 5, "name": "Week 1", "items": []}])

        ntu_fetch.fetch_modules(S(), 9)
        self.assertTrue(seen and seen[0], "no params were sent")
        self.assertIn("include[]", seen[0],
                      f"include[] was not requested: {seen[0]}")
        self.assertEqual(seen[0]["include[]"], "items")


class TestAbsoluteEndpoint(unittest.TestCase):
    """`data-api-endpoint` is not always a URL.

    Measured 2026-10-23: the attribute usually holds an absolute API URL, but
    some assignments carry a bare page slug. Passing that to requests raises
    MissingSchema — the slug is not a URL.
    """

    def test_absolute_url_is_left_alone(self):
        url = "https://cool.ntu.edu.tw/api/v1/courses/9/files/101"
        self.assertEqual(ntu_fetch._absolute_endpoint(url, 9), url)

    def test_bare_slug_becomes_a_page_url(self):
        self.assertEqual(
            ntu_fetch._absolute_endpoint("ke-cheng-da-gang", 9),
            "https://cool.ntu.edu.tw/api/v1/courses/9/pages/ke-cheng-da-gang")

    def test_relative_path_is_made_absolute(self):
        self.assertEqual(
            ntu_fetch._absolute_endpoint("files/101", 9),
            "https://cool.ntu.edu.tw/api/v1/courses/9/files/101")

    def test_leading_slash_is_handled(self):
        self.assertEqual(
            ntu_fetch._absolute_endpoint("/files/101", 9),
            "https://cool.ntu.edu.tw/api/v1/courses/9/files/101")


class TestFetchHandoutBytes(unittest.TestCase):
    """The first hop answers with JSON describing the file, not the file."""

    def test_follows_the_signed_url_for_the_bytes(self):
        import tempfile
        seen = []

        class S:
            def get(self, url, **kw):
                seen.append(url)
                if url.endswith("/files/101"):
                    return _FakeResponse({"url": "https://x/signed",
                                          "display_name": "hw.pdf",
                                          "content-type": "application/pdf"})
                return _FakeResponse(None)

        # download_file needs bytes; give the fake one a real body
        class B:
            status_code = 200
            content = b"%PDF-1.4 fake"
            headers = {"Content-Type": "application/pdf"}
            text = ""

            def raise_for_status(self):
                pass

        class S2(S):
            def get(self, url, **kw):
                seen.append(url)
                if url.endswith("/files/101"):
                    return _FakeResponse({"url": "https://x/signed",
                                          "display_name": "hw.pdf",
                                          "content-type": "application/pdf"})
                return B()

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "hw.pdf")
            res = ntu_fetch.fetch_handout_bytes(
                S2(), "https://cool.ntu.edu.tw/api/v1/courses/9/files/101", dest)
            self.assertIn("path", res, f"no file written: {res}")
            with open(dest, "rb") as f:
                self.assertTrue(f.read().startswith(b"%PDF-"))

    def test_metadata_without_a_url_is_an_error_not_a_crash(self):
        class S:
            def get(self, url, **kw):
                return _FakeResponse({"display_name": "x.pdf"})

        res = ntu_fetch.fetch_handout_bytes(S(), "https://x/files/1", "/tmp/x.pdf")
        self.assertIn("error", res)
        self.assertNotIn("path", res)


class TestCredentialsNeverReachOutput(unittest.TestCase):
    """A credential that gets logged is a leaked credential.

    The password is submitted to ADFS as a form field. If any error path
    printed the request body, the response, or the session's cookies, the
    password would end up in a terminal, a log file, or a CI transcript.

    This is a guard, not a claim: it runs the real login path against a fake
    session and asserts the secret never appears in anything the tool prints.
    """

    SECRET_PASS = "hunter2-not-a-real-password"
    SECRET_USER = "bXXXXXXXX"

    def _capture_login_output(self, fail_at: str) -> str:
        """Run cool_login with a session that fails at a chosen hop."""
        import io
        import contextlib

        class S:
            def __init__(self):
                self.headers = {}

            def get(self, url, **kw):
                if "login/saml" in url:
                    return _FakeResponse({"__html__": "<form></form>"})

                class R:
                    status_code = 200
                    text = "<form action='/x'></form>"
                    headers = {}
                    content = b""

                    def raise_for_status(self):
                        pass
                return R()

            def post(self, url, **kw):
                # The credential is about to be submitted here.
                if fail_at == "post":
                    raise RuntimeError(f"network blew up while posting to {url}")
                class R:
                    status_code = 200
                    text = "<form action='/y'></form>"
                    headers = {}
                    content = b""

                    def raise_for_status(self):
                        pass
                return R()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                ntu_fetch.cool_login(S(), self.SECRET_USER, self.SECRET_PASS)
            except Exception:
                pass
        return buf.getvalue()

    def test_password_never_appears_in_output(self):
        out = self._capture_login_output("post")
        self.assertNotIn(self.SECRET_PASS, out,
                         "the password reached the output")
        self.assertNotIn(self.SECRET_USER, out,
                         "the username reached the output")

    def test_no_debug_mode_that_would_dump_bodies(self):
        """requests' http debug logging prints headers and bodies.

        A stray `enable_http_debugging()` or `debuglevel=1` would put the
        submitted password into stdout.
        """
        src = pathlib.Path(ntu_fetch.__file__).read_text(encoding="utf-8")
        for bad in ("enable_http_debugging", "debuglevel", "response_hook"):
            self.assertNotIn(bad, src,
                             f"{bad} would dump request bodies to stdout")

    def test_credential_file_must_not_be_world_readable(self):
        """A credential file others can read is a leaked credential."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"ntu_user": self.SECRET_USER, "ntu_pass": self.SECRET_PASS}, f)
            path = f.name
        try:
            os.chmod(path, 0o644)
            with self.assertRaises(Exception) as cm:
                ntu_fetch.load_credentials(path)
            self.assertIn("readable by others", str(cm.exception))
            # and it must be readable once the permissions are right
            os.chmod(path, 0o600)
            user, pw = ntu_fetch.load_credentials(path)
            self.assertEqual(pw, self.SECRET_PASS)
        finally:
            os.unlink(path)

    def test_environment_credentials_are_accepted(self):
        """The env-var path leaves no file on disk, so it is the safer one."""
        old_u, old_p = os.environ.get("NTU_USER"), os.environ.get("NTU_PASS")
        os.environ["NTU_USER"] = self.SECRET_USER
        os.environ["NTU_PASS"] = self.SECRET_PASS
        try:
            user, pw = ntu_fetch.load_credentials(None)
            self.assertEqual(user, self.SECRET_USER)
            self.assertEqual(pw, self.SECRET_PASS)
        finally:
            if old_u is None:
                os.environ.pop("NTU_USER", None)
            else:
                os.environ["NTU_USER"] = old_u
            if old_p is None:
                os.environ.pop("NTU_PASS", None)
            else:
                os.environ["NTU_PASS"] = old_p


class TestNoWriteOperations(unittest.TestCase):
    """The tool is read-only. This is the guard that keeps it that way.

    Uploading a submission is the user's own action in a browser. A POST or
    PUT/PATCH/DELETE against course data would be a write against a university
    system under the account of whoever runs this.

    The login chain is the one legitimate POST: submitting a form to
    authenticate is not a write to anything. So the guard is not "no POST
    anywhere" — it is "no write on any course-data endpoint", and the
    exemption for the login hops is explicit.
    """

    WRITE_METHODS = ("post", "put", "patch", "delete")

    def test_fetch_functions_never_write(self):
        """Every function that reads course data issues GET and nothing else.

        `cool_login` is excluded on purpose: it POSTs the SAML form, which is
        authentication, not a write to course data.
        """
        for name in ("fetch_courses", "fetch_all_courses_historical",
                     "fetch_announcements", "fetch_course_files",
                     "fetch_assignments", "fetch_own_submission",
                     "fetch_course_pages", "fetch_modules",
                     "fetch_assignment_handouts",
                     "fetch_announcement_attachments"):
            fn = getattr(ntu_fetch, name)
            src = inspect.getsource(fn)
            for m in self.WRITE_METHODS:
                self.assertNotIn(f".{m}(", src,
                                 f"{name}() issues a {m}() call")

    def test_the_only_posts_are_in_the_login_chain(self):
        """Locate every POST in the module and prove it is a login hop.

        The two that must exist are the ADFS credential form and the SAML
        response. A third POST anywhere would be a write.
        """
        src = pathlib.Path(ntu_fetch.__file__).read_text(encoding="utf-8")
        post_lines = [(i, l) for i, l in enumerate(src.splitlines(), 1)
                      if ".post(" in l]
        self.assertTrue(post_lines, "the login chain should still POST")

        fn = inspect.getsource(ntu_fetch.cool_login)
        for m in self.WRITE_METHODS:
            if m == "post":
                continue
            self.assertNotIn(f".{m}(", fn,
                             f"cool_login() issues a {m}() call")

        # every POST in the file lives inside cool_login
        login_src = fn
        outside = []
        in_login = False
        for i, l in enumerate(src.splitlines(), 1):
            if l.startswith("def cool_login"):
                in_login = True
            elif in_login and l.startswith("def "):
                in_login = False
            if ".post(" in l and not in_login:
                outside.append((i, l.strip()))
        self.assertEqual(outside, [],
                         f"a POST outside the login chain: {outside}")

    def test_session_is_only_ever_asked_for_reads(self):
        calls = []

        class S:
            def get(self, url, **kw):
                calls.append(("GET", url))
                return _FakeResponse([])

            def __getattr__(self, name):
                if name in self.WRITE_METHODS:
                    def bad(*a, **kw):
                        calls.append((name.upper(), a))
                        raise AssertionError(f"{name}() was called")
                    return bad
                raise AttributeError(name)

        ntu_fetch.fetch_assignments(S(), 9)
        ntu_fetch.fetch_modules(S(), 9)
        ntu_fetch.fetch_own_submission(S(), 9, 1)
        self.assertTrue(all(c[0] == "GET" for c in calls),
                        f"a non-GET call happened: {calls}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
