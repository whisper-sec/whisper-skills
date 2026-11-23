#!/usr/bin/env python3
"""Assert that every MCP tool, resource and workflow slug named anywhere in this repo
still exists on the live server, and that the skills stay portable across clients.

This is the check that stops the repo going stale. The previous version of these skills
named four tools that had been removed, and nothing caught it for three months.

The server publishes a fixed tool list per client in its manifest (`toolLists`). A skill is
portable only if every tool it names is on every one of those lists, so files under skills/
are held to the tools all lists share, and may not name a workflow slug at all: they reach
workflows through the named tools. The review cases in plugin.json are held to the same
shared list, because a reviewer runs them in a client that lists only those tools.

No credentials. Both sources are public, so this runs identically on a fork's pull
request and on a maintainer's.

Usage:  python3 scripts/check_surface.py [path ...]
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "whisper-skills-ci/1 (+https://github.com/whisper-sec/whisper-skills)"
MANIFEST = "https://mcp.whisper.security/.well-known/mcp-manifest.json"
GALLERY = "https://www.whisper.security/docs/ai/mcp/workflow-gallery.md"

# The review cases live in the repository root's plugin.json, wherever this runs from.
REVIEW_MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "plugin.json")

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "assets"}
SCAN_EXT = (".md", ".json")

# snake_case tokens in backticks that are field names, parameters or identifier kinds
# rather than tool names. Every entry is a deliberate suppression: add one only with a
# reason, and expect a second reviewer to ask for it.
NOT_TOOL_NAMES = {
    # response fields
    "path_band", "path_coverage",  # whisper.assessUrl columns, named in the cypher patterns
    "data_coverage", "shared_host", "no_data", "known_clean", "structural_only",
    "malicious_evidenced", "first_seen", "last_seen", "row_count", "execution_time",
    "host_class", "vendor_id", "canonical_name", "is_canonical", "sub_labels",
    "k_bucket", "observation_id", "identifier_kind", "promotion_state",
    "deadline_hit", "no_atlas_match", "nearest_known_vendors", "budget_ms",
    # config, headers and OAuth error codes
    "api_key", "user_agent", "content_type", "x_api_key", "allowed_tools",
    "offline_access", "page_size", "core_symlinks", "insufficient_scope",
    "invalid_token", "invalid_client",
}

TOOL_RE = re.compile(r"`(?!whisper[.:])([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
# Tools whose name has no underscore. TOOL_RE cannot tell one from an ordinary backticked
# word, so these are checked by name. A name listed here that the server no longer has is a
# removed tool; a live one-word tool missing from this set would go unchecked once removed,
# so naming one fails until it is added.
ONE_WORD_TOOLS = {"query", "identify"}
WORD_RE = re.compile(r"`([a-z][a-z0-9]+)`")
# Any backticked token shaped like a slug. In a skill, one that names a live workflow fails
# whatever words surround it.
KEBAB_RE = re.compile(r"`([a-z0-9][a-z0-9-]{2,})`")
RESOURCE_RE = re.compile(r"`(whisper://[a-z/]+)`")
# a slug is only claimed as a slug when the text says so, to avoid matching prose
SLUG_RE = re.compile(
    r"""(?:slug|workflow|recipe)[^\n`]{0,24}`([a-z0-9][a-z0-9-]{2,})`"""
    r"""|`([a-z0-9][a-z0-9-]{2,})`\s*(?:slug|workflow|recipe)""",
    re.I,
)


class SurfaceChanged(Exception):
    """The manifest answered, but no longer carries something this check reads: a real change."""


def fetch(url, as_json=True):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if as_json else body


def entry_names(manifest, field, key, default=None):
    entries = manifest.get(field, default)
    if not isinstance(entries, list) or not all(
            isinstance(e, dict) and isinstance(e.get(key), str) for e in entries):
        raise SurfaceChanged("the live manifest's %s is no longer a list of entries with a %s"
                             % (field, key))
    return {e[key] for e in entries}


def gallery_slugs(page):
    """The first column of the slug table under the gallery's "The workflow slugs" heading.

    Other tables on the page, such as a worked example's list of step ids, hold no slugs.
    """
    section = re.search(r"^##\s+The workflow slugs\s*$(.*?)(?=^##\s|\Z)", page, re.M | re.S | re.I)
    slugs = set(re.findall(r"^\|\s*`([a-z0-9][a-z0-9-]{2,})`\s*\|", section.group(1), re.M)
                ) if section else set()
    if not slugs:
        raise SurfaceChanged("the workflow gallery no longer has its slug table under "
                             "\"The workflow slugs\"")
    return slugs


def live_surface():
    manifest = fetch(MANIFEST)
    if not isinstance(manifest, dict):
        raise SurfaceChanged("the live manifest is no longer a JSON object")
    tools = entry_names(manifest, "tools", "name")
    resources = {uri.rstrip("/") for uri in entry_names(manifest, "resources", "uri")}
    prompts = entry_names(manifest, "prompts", "name", default=[])
    lists = manifest.get("toolLists")
    if not isinstance(lists, dict) or not lists or not all(
            isinstance(v, list) and v and all(isinstance(n, str) for n in v)
            for v in lists.values()):
        raise SurfaceChanged("the live manifest no longer publishes toolLists, the per-client "
                             "tool lists, as lists of tool names")
    portable = set.intersection(*(set(v) for v in lists.values()))
    slugs = gallery_slugs(fetch(GALLERY, as_json=False)) | prompts
    return tools, resources, prompts, slugs, portable, sorted(lists)


def in_skills(path):
    parts = os.path.normpath(path).split(os.sep)
    return "skills" in parts[:-1]


def tool_problem(token, tools, portable, skill_file):
    """What is wrong with a tool name, or None when the live server lists it where it is used."""
    if token not in tools:
        return "`%s` is not a live MCP tool (live: %s)" % (token, ", ".join(sorted(tools)))
    if skill_file and token not in portable:
        return ("`%s` is not on every client's tool list, so a skill cannot rely on it "
                "(on every list: %s)" % (token, ", ".join(sorted(portable))))
    return None


def scan(paths, tools, resources, slugs, portable):
    fails = []
    files = []
    for root in paths:
        if not os.path.exists(root):
            fails.append("%s: no such file or directory, so nothing in it was checked" % root)
            continue
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [
                os.path.join(dirpath, f) for f in filenames if f.endswith(SCAN_EXT)
            ]

    for path in sorted(set(files)):
        text = open(path, encoding="utf-8", errors="replace").read()
        skill_file = in_skills(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            words = WORD_RE.findall(line)
            named = [t for t in TOOL_RE.findall(line) if t not in NOT_TOOL_NAMES]
            for token in named + [t for t in words if t in ONE_WORD_TOOLS]:
                problem = tool_problem(token, tools, portable, skill_file)
                if problem:
                    fails.append("%s:%d: %s" % (path, lineno, problem))
            for token in words:
                if token in tools and token not in ONE_WORD_TOOLS:
                    fails.append(
                        "%s:%d: `%s` is a live one-word tool this check does not track: add it "
                        "to ONE_WORD_TOOLS so its removal is caught" % (path, lineno, token)
                    )
            if skill_file:
                for token in KEBAB_RE.findall(line):
                    if token in slugs and token not in tools:
                        fails.append(
                            "%s:%d: workflow slug '%s' named in a skill; skills reach workflows "
                            "through the named tools" % (path, lineno, token)
                        )
            for uri in RESOURCE_RE.findall(line):
                if uri.rstrip("/") not in resources:
                    fails.append(
                        "%s:%d: resource %s is not advertised by the server" % (path, lineno, uri)
                    )
            for match in SLUG_RE.findall(line):
                slug = match[0] or match[1]
                if slug and slug not in slugs and slug not in tools:
                    fails.append(
                        "%s:%d: workflow slug '%s' is not in the live gallery"
                        % (path, lineno, slug)
                    )
    return fails


def review_cases(portable, path=REVIEW_MANIFEST):
    """Every tool a review case expects must be one a reviewer's client lists.

    Only the tool names are read here; check_manifests.py holds the cases to their shape.
    """
    shown = os.path.relpath(path)
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        return ["%s: the review cases could not be read: %s" % (shown, exc)]
    openai = (manifest.get("extensions") or {}).get("com.openai") if isinstance(manifest, dict) else None
    review = openai.get("review") if isinstance(openai, dict) else None
    cases = review.get("test_cases") if isinstance(review, dict) else None
    fails = []
    for kind, entries in sorted(cases.items()) if isinstance(cases, dict) else ():
        for i, case in enumerate(entries if isinstance(entries, list) else []):
            named = case.get("tools_triggered") if isinstance(case, dict) else None
            if not isinstance(named, str):
                continue
            for tool in (t.strip() for t in named.split(",")):
                if tool and tool not in portable:
                    fails.append(
                        "%s: review.test_cases.%s[%d] expects `%s`, which is not on every "
                        "client's tool list" % (shown, kind, i, tool)
                    )
    return fails


def main(paths):
    try:
        tools, resources, prompts, slugs, portable, lists = live_surface()
    except SurfaceChanged as exc:
        # Not an outage, so it must not read as inconclusive.
        print("FAIL %s" % exc)
        return 1
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
        print("ERROR: could not read the live surface: %s" % exc)
        print("This check needs network access to two public URLs and no credentials.")
        return 2

    print(
        "live surface: %d tools, %d on every client list (%s), %d resources, %d prompts, "
        "%d gallery slugs"
        % (len(tools), len(portable), ", ".join(lists), len(resources), len(prompts), len(slugs))
    )
    fails = scan(paths, tools, resources, slugs, portable) + review_cases(portable)
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["skills", "agents", "commands", "README.md"]))
