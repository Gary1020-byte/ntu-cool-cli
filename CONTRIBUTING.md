# Contributing to ntu-course-announcements

Thanks for considering a contribution. This is a **read-only** fetcher for NTU
Cool course announcements and course files.

## The constraint: read-only, and it stays that way

This tool logs in with your NTU credentials to *read* announcements. It must
never write, post, comment, or modify anything on cool.ntu.edu.tw. If a
contribution would add a write path, it will not be merged — not as a style
preference, but because the tool is used against a university system under the
account of the person running it.

## The constraint: no BeautifulSoup

The script deliberately uses `html.parser` from the stdlib instead of
`beautifulsoup4`. The two things it needs from an HTML parser — "find a form,
read its inputs" and "flatten visible text" — are about twenty lines of
`HTMLParser`. Keeping the parser dependency-free means the script runs on
whatever interpreter the user has, without a resolver fighting them.

`requests` is the only third-party import, and that is deliberate too.

## Getting set up

```bash
git clone https://github.com/Gary1020-byte/ntu-course-announcements.git
cd ntu-course-announcements
python3 -m pip install -r requirements.txt
```

Requires Python 3.9 or newer.

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

All 53 tests are **offline**: no network, no credentials, no login, and they
can never reach cool.ntu.edu.tw. They run in milliseconds, so run them before
every commit.

CI runs the suite on Python 3.9, 3.10, 3.11, and 3.12 — 3.9 is the floor
declared in `pyproject.toml`, so the floor is what gets tested.

## What a good contribution looks like

**A bug fix should come with a test.** The tests in `tests/test_ntu_fetch.py`
each correspond to a bug that was actually shipped and fixed. The important
ones were the silent ones: a pagination bug that quietly dropped 30% of
files, and a hardcoded `json.loads(r.text[9:])` slice that happened to work
until the prefix changed.

If you fix a bug, write the test that fails before the fix and passes after.

**Don't add a network call to the test suite.** Use inline fixtures — see
`TestParseJsonLoose` and `TestParseFirstForm` for the pattern.

**Don't add a dependency without discussing it first.** Open an issue and
explain what the stdlib can't do. The one-dependency install is a feature.

## Credentials — the important rule

Credentials live in a JSON file you pass with `--cred-file`. They must never
appear in:

- a commit, a commit message, or a branch name
- an issue or a pull-request body
- a log line, an error message, or a traceback
- the README or any other tracked file

The tool refuses to read a credential file with loose permissions. If you
paste a signed Cool URL into an issue, it is a leaked credential — the
`verifier=` query parameter **is** the credential. Strip it before pasting, or
delete the comment.

If you accidentally commit a credential, say so immediately rather than
quietly rewriting history — a rewrite does not un-leak a credential that was
already pushed.

## Reporting bugs

Open an issue with:

- The command you ran
- What you expected and what happened instead
- Your Python version and OS
- The output of the command with any credential redacted

## Pull requests

- Branch from `main`, one topic per PR.
- Make sure `python3 -m unittest discover -s tests -v` passes locally.
- Describe what changed and why. If it fixes a bug, say what the bug was.

## License

By contributing, you agree that your contributions are licensed under the MIT
License.
