#!/usr/bin/env python3
"""Assert that every MCP tool, resource and workflow slug named anywhere in this repo
still exists on the live server.

This is the check that stops the repo going stale. The previous version of these skills
named four tools that had been removed, and nothing caught it for three months.

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

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "assets"}
SCAN_EXT = (".md", ".json")

# snake_case tokens in backticks that are field names, parameters or identifier kinds
# rather than tool names. Every entry is a deliberate suppression: add one only with a
# reason, and expect a second reviewer to ask for it.
NOT_TOOL_NAMES = {
    # response fields
    "data_coverage", "shared_host", "no_data", "known_clean", "structural_only",
    "malicious_evidenced", "first_seen", "last_seen", "row_count", "execution_time",
    "host_class", "vendor_id", "canonical_name", "is_canonical", "sub_labels",
    "k_bucket", "observation_id", "identifier_kind", "promotion_state",
    "deadline_hit", "no_atlas_match", "nearest_known_vendors", "budget_ms",
    # submit identifier kinds
    "host_hash_rotating", "url_path_hash", "cert_sha256", "cert_ja3_hash",
    "cert_ja4_hash", "cert_jarm", "whois_pattern", "submit_write",
    # config, headers and OAuth error codes
    "api_key", "user_agent", "content_type", "x_api_key", "allowed_tools",
    "offline_access", "page_size", "core_symlinks", "insufficient_scope",
    "invalid_token", "invalid_client",
}

TOOL_RE = re.compile(r"`(?!whisper[.:])([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
RESOURCE_RE = re.compile(r"`(whisper://[a-z/]+)`")
# a slug is only claimed as a slug when the text says so, to avoid matching prose
SLUG_RE = re.compile(
    r"""(?:slug|workflow|recipe)[^\n`]{0,24}`([a-z0-9][a-z0-9-]{2,})`"""
    r"""|`([a-z0-9][a-z0-9-]{2,})`\s*(?:slug|workflow|recipe)""",
    re.I,
)


def fetch(url, as_json=True):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if as_json else body


def live_surface():
    manifest = fetch(MANIFEST)
    tools = {t["name"] for t in manifest.get("tools", [])}
    resources = {r["uri"].rstrip("/") for r in manifest.get("resources", [])}
    prompts = {p["name"] for p in manifest.get("prompts", [])}
    gallery = fetch(GALLERY, as_json=False)
    slugs = set(re.findall(r"^\|\s*`?([a-z0-9][a-z0-9-]{2,})`?\s*\|", gallery, re.M)) | prompts
    return tools, resources, prompts, slugs


def scan(paths, tools, resources, slugs):
    fails = []
    files = []
    for root in paths:
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
        for lineno, line in enumerate(text.splitlines(), 1):
            for token in TOOL_RE.findall(line):
                if token in NOT_TOOL_NAMES or token in tools:
                    continue
                fails.append(
                    "%s:%d: `%s` is not a live MCP tool (live: %s)"
                    % (path, lineno, token, ", ".join(sorted(tools)))
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


def main(paths):
    try:
        tools, resources, prompts, slugs = live_surface()
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
        print("ERROR: could not read the live surface: %s" % exc)
        print("This check needs network access to two public URLs and no credentials.")
        return 2

    print(
        "live surface: %d tools, %d resources, %d prompts, %d gallery slugs"
        % (len(tools), len(resources), len(prompts), len(slugs))
    )
    fails = scan(paths, tools, resources, slugs)
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["skills", "agents", "commands", "README.md"]))
