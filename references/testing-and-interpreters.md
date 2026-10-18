# Testing this skill — run with the SAME python you will use

This bit the original author on 2026-10-18 and it will bite anyone else running it by hand.

`ntu_fetch.py` was first exercised under Hermes' own interpreter, which ships
`beautifulsoup4`. The system `python3` does not. When the user ran it from his shell:

```
ModuleNotFoundError: No module named 'bs4'
  File ".../ntu_fetch.py", line 126, in cool_login
```

It surfaced as a traceback inside the login function, which reads like a code
defect. It was an environment assumption.

## The fix that removed the problem rather than documenting it

`bs4` is now **not a dependency at all**. The two things the script needed it for:

| need | replacement |
|---|---|
| flatten visible text | `_TextOnly(HTMLParser)` — stdlib, skips script/style/head |
| read a form's action + inputs | `_FormOnly(HTMLParser)` — stdlib |

`requests` is the only third-party import now. `html.parser` ships with every
Python, so the interpreter question disappears.

## Verify against both interpreters when changing anything

```bash
# whichever python your agent runtime uses (may ship extra packages)
python3 scripts/ntu_fetch.py --probe

# the system python a human types at a shell prompt
/usr/bin/python3 scripts/ntu_fetch.py --probe   # or: /usr/local/bin/python3 ...
```

If a change works under the first and not the second, it is a dependency problem,
not a logic problem. `which python3` on this machine returns Hermes' toolchain
first, so an unqualified `python3` in a test harness silently tests the wrong one.

## A real bug the stdlib swap exposed

`_FormOnly` initially captured the first form to *close* rather than the first to
*open*. BeautifulSoup's `find("form")` returns the first in document order, and
login pages routinely park a hidden trap form in `<head>`:

```html
<head><form action="/adfs/ls/?wa=wsignin1.0" style="display:none"> ... </form></head>
<body><form action="/login/callback"> ... real credentials ... </form></body>
```

Capturing on close would post the credentials to the trap form's action. The
parser now stops at the second `<form>` start instead. This class of bug is
exactly what "replace a library with the stdlib" is for — the swap made the
semantics explicit and testable.

## Assertion direction can be wrong too

The first test written for this pass asserted that the parser picks the *second*
form (written while the bug was still present), so it "passed" against broken
code. Five of its assertions were wrong, not the code. When a new test fails,
check whether the expectation was written against observed behaviour before
changing the implementation.