# Releasing and packaging the CLI

The tool ships two ways, and they drift apart on purpose:

| path | gives you |
|---|---|
| `pipx install ntu-cool-cli` / `uv tool install ntu-cool-cli` | the **published** version on PyPI |
| `uv tool install 'git+https://github.com/Gary1020-byte/ntu-cool-cli.git'` | the **repo tip**, unreleased |

## A wheel in `dist/` is not a release

`dist/ntu_cool_cli-<version>-py3-none-any.whl` and `.tar.gz` are build artifacts in
the working tree. They prove a build succeeded; they prove nothing about PyPI.
The two get out of sync routinely — the tree can carry a bumped version whose
artifacts are built but never uploaded.

So never tell the user 「新版本已上架」 because the version number in
`pyproject.toml` or in `dist/` moved. Confirm the publish separately:

```bash
pipx list                       # installed version
curl -s https://pypi.org/pypi/ntu-cool-cli/json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); print(d["info"]["version"])'
```

Two independent readings — the installed one and the index one — is the only
way to state 「已上架」 as a fact.

## When the user says 「修好它」

Check which surface he means before editing, because the fix location differs:

- a **behaviour** bug (wrong endpoint, wrong parsing, wrong pagination) → fix
  `scripts/ntu_fetch.py`, add a test, bump the version, rebuild, publish.
- an **installed-tool** complaint (「`ntu-cool-cli` 跑起來不是最新」) → this is
  usually a version-skew problem, not a code problem: the installed copy comes
  from PyPI while the fix sits in the working tree. Fix in the repo first, then
  publish; reinstalling before publishing installs the same old version.

## Release checklist

1. Offline tests first — `python3 -m unittest discover -s tests` needs no
   credentials and gates everything else.
2. Bump the version in `pyproject.toml`.
3. Build the sdist and the wheel.
4. Publish to PyPI (the repo carries a dedicated publish workflow).
5. Verify from the index, not from the local file (§ A wheel in `dist/` …).
6. `CHANGELOG.md` gets the entry; the READMEs carry the install command near
   the top.

## Branches

Work happens on feature branches (`feat/…`) and merges into `main`. A fix that
lives only on a feature branch is not released — `pipx install` reads PyPI,
which is fed from `main`. Before claiming a fix is live, confirm it is on
`main` **and** published.

## Credentials for publishing

The publish workflow uses PyPI trusted publishing (OIDC), but no matching
publisher is registered on PyPI for owner `Gary1020-byte`, repo `ntu-cool-cli`,
and workflow `publish.yml`. Trusted publishing is intentionally not registered
at the moment, so the workflow fails at `Publish to PyPI` with
`invalid-publisher: valid token, but no corresponding publisher` until that
account-level setting changes. It has failed on all five releases so far:
v1.3.1 (run 40116362281), v1.3.2 (40119970745), v1.3.3 (40509977886), v1.3.4
(40530382650), and v1.3.5 (40533348823); the workflow has never published
successfully. All five versions are on PyPI because they were uploaded by hand,
and the red CI runs did not block any release.

The upload is irreversible: a filename cannot be re-uploaded under the same
version. If a run fails after a partial upload, check PyPI before retrying it;
do not blindly re-run. `NTU_USER`/`NTU_PASS` are unrelated to publishing.
