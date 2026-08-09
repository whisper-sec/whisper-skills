#!/usr/bin/env python3
"""Validate every Cypher block in the repo against the live graph.

No credentials. The public graph API answers keyless, and EXPLAIN is not subject to the
keyless traversal-depth cap, so a deep pattern can be planned by anyone — including a
fork's pull request, which has no secrets.

Two layers, because one is not enough:

  1. EXPLAIN over the public API — catches syntax errors and write clauses, and flags
     any query the server had to rewrite. A rewrite is a FAILURE here: the shipped
     pattern is wrong even though the server was forgiving about it.
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
    fails = []
    for group in LABEL_RE.findall(cypher):
        for label in group.split("|"):
            if label not in labels:
                fails.append("%s block#%d: unknown label :%s" % (path, index, label))
    for group in EDGE_RE.findall(cypher):
        for edge in group.split("|"):
            if edge not in edges:
                fails.append("%s block#%d: unknown edge type [:%s]" % (path, index, edge))

    result = api("EXPLAIN " + cypher.strip().rstrip(";"))
    if result.get("rewrittenQuery") or result.get("advisories"):
        advisories = result.get("advisories") or [{"message": "the query was rewritten"}]
        for advisory in advisories:
            message = advisory.get("message", "") if isinstance(advisory, dict) else advisory
            fails.append(
                "%s block#%d: the server rewrote this query — %s" % (path, index, str(message)[:160])
            )
    if "rows" not in result and "columns" not in result:
        detail = result.get("detail") or result.get("title") or json.dumps(result)[:200]
        fails.append("%s block#%d: %s" % (path, index, detail))
    return fails


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
    fails, checked, skipped = [], 0, 0
    for path in markdown_files(paths):
        text = open(path, encoding="utf-8", errors="replace").read()
        for index, (illustrative, body) in enumerate(BLOCK_RE.findall(text), 1):
            if illustrative:
                skipped += 1
                continue
            checked += 1
            try:
                fails += check_block(path, index, body, labels, edges)
            except Unreachable as exc:
                print("UNREACHABLE: stopped at %s block#%d — %s" % (path, index, exc))
                print("This is an outage or a rate limit, not a defect in this repository.")
                return UNREACHABLE

    print("checked %d block(s), skipped %d illustrative" % (checked, skipped))
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    # Exit codes are load-bearing: 0 clean, 1 a real defect, 2 the endpoint was
    # unreachable. CI must not open a drift issue on a 2.
    sys.exit(main(sys.argv[1:] or ["skills"]))
