#!/usr/bin/env python3
"""Refuse to ship a graph statistic in prose.

Node counts, edge counts, feed counts, label counts and rule counts drift continuously,
and the published documentation pages have disagreed with each other about them. A number
written into a skill is a number that will be wrong, and — worse than wrong — wrong
silently, because nothing fails when it drifts.

The rule: if the server can return it, do not write it down. Fetch it at runtime.

Offline. No network, no credentials.

Usage:  python3 scripts/check_no_counts.py [path ...]
"""
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "assets"}
SCAN_EXT = (".md",)

MAGNITUDE = r"(?:~?\d[\d,._]*\s*(?:billion|million|thousand|B|M|K)\b|\d[\d,]{2,})"
WORD_NUMBER = r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
# verbs and determiners that turn a number into a claim about inventory
CLAIMING = (
    r"(?:holds?|contains?|has|have|spans?|ships?|exposes?|advertises?|covers?|"
    r"comprises?|there are|all|the|its|only|both|these|those|across|over|of)"
)

SUBJECTS = (
    r"nodes?|edges?|relationships?|node labels?|edge types?|"
    r"relationship types?|feed sources?|threat[- ]intel(?:ligence)? edges?|"
    r"threat feeds?|categories|hostnames?|IP addresses|prefixes|organi[sz]ations?|"
    r"MCP tools?|read tools?|write tools?|prompts?|MCP resources?|"
    r"workflows?|recipes?|gallery (?:workflows?|recipes?|entries)|"
    r"(?:query[- ]safety|validation|safety) rules?|layers?"
)

PATTERNS = [
    # "7.4 billion nodes", "10.8M threat-intel edges", "2,730,258,219 hostnames", "76 feed sources"
    (re.compile(r"\b%s\+?\s+(?:%s)\b" % (MAGNITUDE, SUBJECTS), re.I),
     "a graph magnitude"),
    # "the nine validation rules", "all 12 workflows", "ships nine tools"
    (re.compile(r"\b%s\s+%s\s+(?:%s)\b" % (CLAIMING, WORD_NUMBER, SUBJECTS), re.I),
     "a countable inventory"),
    # "the graph holds 40 labels", "there are 9 tools"
    (re.compile(r"\b(?:holds|contains|spans|ships|exposes|advertises|there are)\s+"
                r"(?:roughly |about |around |over |more than |~)?%s\s" % WORD_NUMBER, re.I),
     "an inventory claim"),
]

# Numbers that are not graph statistics. Each needs a reason.
ALLOW_LINE = re.compile(
    r"(?:"
    r"^\s*\|"                       # table rows: the tables here are rules, not counts
    r"|\[\*1\.\.\d"                 # bounded path syntax
    r"|LIMIT \d"                    # Cypher literals
    r"|HTTP/?\d|:\d{2,5}\b"         # protocol and ports
    r"|\bstep 1\b|\bstep 2\b|\bstep 3\b|\bstep 4\b|\bstep 5\b"
    r"|\bone level deep\b|\bone call\b|\bone pass\b|\bone line\b|\bone sentence\b"
    r"|\bone at a time\b|\bone request at a time\b|\bone indicator\b|\bone domain\b"
    r"|\bone column\b|\bone table\b|\bone hop\b|\bone place\b|\bone thing\b"
    r"|\bone bulk call\b|\bone plugin\b|\bone marketplace\b|\bone endpoint\b"
    r"|\bno-counts?\b"
    r")",
    re.I,
)
ALLOW_MARK = "<!-- counts-ok:"


def scan_file(path):
    fails = []
    in_fence = False
    for lineno, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or ALLOW_MARK in line or ALLOW_LINE.search(line):
            continue
        for pattern, kind in PATTERNS:
            match = pattern.search(line)
            if match:
                fails.append(
                    "%s:%d: %s in prose — %r. Read it from the server instead, or add "
                    "%s reason --> on the line."
                    % (path, lineno, kind, match.group(0).strip(), ALLOW_MARK)
                )
                break
    return fails


def main(paths):
    files = []
    for root in paths:
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [os.path.join(dirpath, f) for f in filenames if f.endswith(SCAN_EXT)]

    fails = []
    for path in sorted(set(files)):
        fails += scan_file(path)
    print("scanned %d file(s)" % len(set(files)))
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["skills", "agents", "commands"]))
