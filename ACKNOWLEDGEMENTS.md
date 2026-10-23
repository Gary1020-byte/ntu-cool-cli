# Acknowledgements

## Attribution

The SAML login sequence for cool.ntu.edu.tw and the shape of the announcement
list response were not written down anywhere public. They were learned by
reading the source of an earlier community project,
[`brianbbsu/NTU-Announcement-Crawler`](https://github.com/brianbbsu/NTU-Announcement-Crawler)
(created 2019-09-25), and are credited here.

**No code was taken from it.** `ntu_fetch.py` is a ground-up reimplementation
with a different structure — no Flask, no SQLAlchemy, no daemon, no Telegram
bot. The two designs that were worth keeping, content-hash dedupe and a
presence flag for soft deletes, are described in `references/api-findings.md`
as ideas to copy, not as code.

That project carries **no LICENSE file**, so its code cannot be redistributed.
None of it was. What was learned from reading it is credited above; the
implementation is original.

Everything else in `references/api-findings.md` was measured against the live
site in October 2026 and is a fact about the platform, not about that project.
