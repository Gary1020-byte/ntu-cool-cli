# Ceiba scraping — unreachable from this host

## The fact

```
ceiba.ntu.edu.tw  →  DNS resolves to 140.112.161.178
                  →  HTTPS connect: TIMEOUT (15s)
                  →  HTTP  connect: TIMEOUT (20s, HTTP 000)
```

Control test, same minute, same client:

```
www.ntu.edu.tw    HTTP 200  0.048s
cool.ntu.edu.tw   HTTP 302  0.033s
adfs.ntu.edu.tw   HTTP 200  0.137s
ceiba.ntu.edu.tw  timeout
```

## What this rules out

- **Not DNS.** The name resolves; an A record is returned immediately.
- **Not a network path or routing problem.** Three sibling NTU hosts on the same
  infrastructure answer in under 150ms from the same client at the same moment.
- **Not an NTU-wide outage.** cool, adfs, and www are all up.
- **Not TLS.** The TCP handshake itself never completes — port 443 is filtered, so no
  certificate is ever negotiated.

## What remains

Something filters that one host from this server. Candidates, in order of likelihood:

1. **A source-range ACL on NTU's side.** This server is on residential/campus-adjacent
   infrastructure in Taiwan; ceiba may be restricted to campus or VPN ranges.
2. **A blocklist entry** specific to ceiba.ntu.edu.tw.
3. An upstream network-level filter between this host and 140.112.161.178 specifically.

There is no way to distinguish these from outside, and it is not worth the effort to — the
NTU Cool path covers the actual need.

## Consequences for the fetcher

- `ntu_fetch.py` implements **only** the NTU Cool path. A Ceiba crawler would be
  untestable code: written, never successfully run, and therefore never verified.
- `--probe` reports Ceiba as a known-unreachable baseline, not as a fresh failure. Do not
  report "Ceiba crawling failed" as if it were a regression.
- If Ceiba ever becomes necessary, the fix is a network change (on-campus or VPN), not a
  code change. Reachability must be confirmed with `--probe` before writing any Ceiba
  code.

## Upstream Ceiba parser, for the record

`brianbbsu/NTU-Announcement-Crawler` does include a `CeibaCrawler`, parsing with hard table
indices:

```python
rows[0].find("td").string   # title
rows[1].find("td").string   # date
rows[5].find("td")          # content
```

Positional indexing like this silently mis-assigns fields if a row is added or removed — a
title lands in the body, or an IndexError from a vanished row. Even with reachability
restored this would need verification against a live page before its output could be
trusted. Two independent reasons not to build on it yet.