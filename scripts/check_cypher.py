#!/usr/bin/env python3
"""Validate every Cypher block in the repo against the live graph.

No credentials. The public graph API answers keyless, and EXPLAIN is not subject to the
keyless traversal-depth cap, so a deep pattern can be planned by anyone — including a
fork's pull request, which has no secrets.

Two layers, because one is not enough:

  1. EXPLAIN over the public API — catches syntax errors and write clauses, and flags
     any query the server had to rewrite or qualify. A rewrite or an advisory is a
     FAILURE here: the shipped pattern is wrong even though the server was forgiving
     about it. One family is exempt, because it describes the caller rather than the
     pattern: the engine qualifies any statement that names contact data when the
     caller lacks the contact-data entitlement, and a keyless check never has it. The
     plan still comes back, so such a block is checked like any other and listed as
     needing the entitlement to run.
  2. Token cross-check against the live label and relationship-type listings. EXPLAIN
     will happily plan a query naming an edge type or a property that does not exist,
     so layer 1 alone would pass a pattern that silently returns nothing forever.

What this does NOT prove: the public API does not enforce the connector's query-safety
rules, and its response envelope carries none of the connector's self-correction fields.
A block that passes here can still be rejected by the connector.

Blocks fenced ```cypher-illustrative are deliberately wrong and are skipped.

Usage:  python3 scripts/check_cypher.py [path ...]
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

UA = "whisper-skills-ci/1 (+https://github.com/whisper-sec/whisper-skills)"
API = "https://graph.whisper.security/api/query"
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "assets"}

# The keyless tier allows one query at a time and a bounded number per hour, and this
# script makes one request per Cypher block. Pace it, and back off rather than failing a
# build over a rate limit — a throttled run is an inconclusive run, not a broken repo.
PACE_SECONDS = 0.4
MAX_ATTEMPTS = 4
UNREACHABLE = 2

# Real and traversable, but synthesised only when an endpoint is anchored, so absent
# from the relationship-type listing. Keep this list short, and re-check it when the
# nightly job reports drift. Last confirmed: 2026-08-09.
EXTRA_EDGES = {"PARENT_OF"}

# Advisories about the caller's plan, not the pattern. The engine attaches them to any
# statement that names contact data (an EMAIL or PHONE label, a HAS_EMAIL or HAS_PHONE
# edge) when the caller lacks the contact-data entitlement, which a keyless check never
# has. Keep this to entitlement kinds: every other advisory still fails the block.
ENTITLEMENT_KINDS = {"contact-data-not-entitled", "contact-data-withheld"}

BLOCK_RE = re.compile(r"```cypher(-illustrative)?\n(.*?)```", re.S)
LABEL_RE = re.compile(r"(?<![\w$])\(\s*\w*\s*:([A-Z][A-Z0-9_|]*)")
EDGE_RE = re.compile(r"\[\s*\w*\s*:([A-Z][A-Z0-9_|]*)")
PARAM_RE = re.compile(r"\$([A-Za-z_]\w*)")


class Unreachable(Exception):
    """The endpoint could not be reached or kept throttling. Not a repo defect."""


def api(cypher, parameters=None):
    payload = {"query": cypher}
    if parameters:
        payload["parameters"] = parameters
    body = json.dumps(payload).encode("utf-8")
    delay = 2.0
    last = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        time.sleep(PACE_SECONDS)
        request = urllib.request.Request(
            API,
            data=body,
            method="POST",
            headers={"User-Agent": UA, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                last = "HTTP %s" % exc.code
            else:
                try:
                    return json.loads(exc.read())
                except ValueError:
                    return {"title": "HTTP %s" % exc.code, "detail": str(exc.reason)}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = str(getattr(exc, "reason", exc)) or exc.__class__.__name__
        if attempt < MAX_ATTEMPTS:
            print("  … %s, retrying in %.0fs" % (last, delay))
            time.sleep(delay)
            delay *= 2
    raise Unreachable(last)


def live_schema():
    labels = api("CALL db.labels() YIELD label RETURN collect(label) AS l")
    edges = api("CALL db.relationshipTypes() YIELD type RETURN collect(type) AS t")
    label_rows = labels.get("rows") if isinstance(labels, dict) else None
    edge_rows = edges.get("rows") if isinstance(edges, dict) else None
    if not label_rows or not edge_rows:
        raise RuntimeError("could not read the live schema: %s" % json.dumps(labels)[:300])
    first_labels, first_edges = label_rows[0], edge_rows[0]
    if not isinstance(first_labels, dict) or not isinstance(first_edges, dict):
        raise RuntimeError("unexpected schema row shape")
    return set(first_labels["l"]), set(first_edges["t"]) | EXTRA_EDGES


def check_block(path, index, cypher, labels, edges):
    """Return (fails, notes) for one block. A note never fails the build."""
    fails, notes = [], []
    for group in LABEL_RE.findall(cypher):
        for label in group.split("|"):
            if label not in labels:
                fails.append("%s block#%d: unknown label :%s" % (path, index, label))
    for group in EDGE_RE.findall(cypher):
        for edge in group.split("|"):
            if edge not in edges:
                fails.append("%s block#%d: unknown edge type [:%s]" % (path, index, edge))

    result = api("EXPLAIN " + cypher.strip().rstrip(";"))
    if result.get("rewrittenQuery"):
        fails.append(
            "%s block#%d: the server rewrote this query to: %s"
            % (path, index, str(result["rewrittenQuery"])[:160])
        )
    entitlement = set()
    for advisory in result.get("advisories") or []:
        kind = advisory.get("kind") if isinstance(advisory, dict) else None
        if kind in ENTITLEMENT_KINDS:
            entitlement.add(kind)
            continue
        message = advisory.get("message", "") if isinstance(advisory, dict) else advisory
        fails.append(
            "%s block#%d: server advisory %s: %s"
            % (path, index, kind or "with no kind", str(message)[:160])
        )
    if "rows" not in result and "columns" not in result:
        detail = result.get("detail") or result.get("title") or json.dumps(result)[:200]
        fails.append("%s block#%d: %s" % (path, index, detail))
    elif entitlement:
        notes.append(
            "%s block#%d: planned; running it needs the contact-data entitlement (%s)"
            % (path, index, ", ".join(sorted(entitlement)))
        )
    return fails, notes


def markdown_files(paths):
    files = []
    for root in paths:
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [os.path.join(dirpath, f) for f in filenames if f.endswith(".md")]
    return sorted(set(files))


def main(paths):
    try:
        labels, edges = live_schema()
    except (Unreachable, urllib.error.URLError, RuntimeError, ValueError, KeyError, IndexError) as exc:
        print("UNREACHABLE: could not read the live schema — %s" % exc)
        print("This is an outage or a rate limit, not a defect in this repository.")
        return UNREACHABLE

    print("live schema read: labels and relationship types (extra: %s)" % sorted(EXTRA_EDGES))
    fails, notes, checked, skipped = [], [], 0, 0
    for path in markdown_files(paths):
        text = open(path, encoding="utf-8", errors="replace").read()
        for index, (illustrative, body) in enumerate(BLOCK_RE.findall(text), 1):
            if illustrative:
                skipped += 1
                continue
            checked += 1
            try:
                block_fails, block_notes = check_block(path, index, body, labels, edges)
            except Unreachable as exc:
                print("UNREACHABLE: stopped at %s block#%d — %s" % (path, index, exc))
                print("This is an outage or a rate limit, not a defect in this repository.")
                return UNREACHABLE
            fails += block_fails
            notes += block_notes

    print("checked %d block(s), skipped %d illustrative" % (checked, skipped))
    for n in notes:
        print("NOTE", n)
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    # Exit codes are load-bearing: 0 clean, 1 a real defect, 2 the endpoint was
    # unreachable. CI must not open a drift issue on a 2.
    sys.exit(main(sys.argv[1:] or ["skills"]))
