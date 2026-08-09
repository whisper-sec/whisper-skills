#!/usr/bin/env python3
"""Check that every link in the repo resolves.

Relative links are checked on disk. External links are fetched with HEAD, falling back to
a ranged GET for servers that reject HEAD. The previous version of this repo was linked
from a public documentation page that had gone stale; a dead link is a defect that costs
every reader, and it is cheap to catch.

No credentials. Pass --offline to skip the network half.

Usage:  python3 scripts/check_links.py [--offline] [path ...]
"""
import ipaddress
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

UA = "whisper-skills-ci/1 (+https://github.com/whisper-sec/whisper-skills)"
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}

# This runs on pull requests, including from forks, and it fetches whatever URLs the tree
# names. Two guards: never contact a non-public address, and never make an unbounded
# number of requests because someone added a file full of them.
MAX_URLS = 200
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BARE_URL_RE = re.compile(r"(?<![(\[<])\bhttps://[^\s`\"'>)\],]+")
# The manifests carry homepage and repository URLs that no markdown scan would ever see,
# and a plugin listing that points at a repository nobody can reach is a review failure.
MANIFEST_FILES = (".json", ".yml", ".yaml")

# A link is dead when the resource is not there. It is NOT dead when the host answers with
# "wrong method" or "authenticate first" — several of the URLs in this repo are API
# endpoints, and the connector deliberately has no anonymous mode, so a 401 from it is the
# documented behaviour rather than a broken link.
# A redirect means the resource is there. Note that Python's urllib does not follow 308
# on its own, so it surfaces here as an error rather than being resolved silently.
ALIVE_CODES = {301, 302, 303, 307, 308, 400, 401, 403, 405, 406, 409, 422, 429}
DEAD_CODES = {404, 410}


def is_public(url):
    """False when the host resolves to a private, loopback, link-local or reserved address."""
    host = urlsplit(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True  # unresolvable — let the fetch report it as a dead link
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            return False
    return True


def check_url(url):
    if urlsplit(url).scheme not in ("http", "https"):
        return "unsupported scheme"
    if not is_public(url):
        return "resolves to a non-public address; refusing to fetch"
    last = None
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": UA, "Accept": "*/*"}
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                if response.status < 400:
                    return None
                last = "HTTP %s" % response.status
        except urllib.error.HTTPError as exc:
            if exc.code in ALIVE_CODES:
                return None
            if exc.code in DEAD_CODES:
                return "HTTP %s" % exc.code
            last = "HTTP %s" % exc.code
        except (urllib.error.URLError, OSError) as exc:
            last = str(getattr(exc, "reason", exc))
    return last


def main(argv):
    offline = "--offline" in argv
    paths = [a for a in argv if not a.startswith("--")] or ["."]

    files = []
    for root in paths:
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [
                os.path.join(dirpath, f)
                for f in filenames
                if f.endswith(".md") or f.endswith(MANIFEST_FILES)
            ]

    fails = []
    external = {}
    for path in sorted(set(files)):
        base = os.path.dirname(path)
        text = open(path, encoding="utf-8", errors="replace").read()
        if path.endswith(MANIFEST_FILES):
            for url in BARE_URL_RE.findall(text):
                external.setdefault(url.rstrip("."), []).append(path)
            continue
        for target in LINK_RE.findall(text):
            if target.startswith("#") or target.startswith("mailto:"):
                continue
            if target.startswith(("http://", "https://")):
                external.setdefault(target.rstrip("."), []).append(path)
                continue
            local = target.split("#", 1)[0]
            if local and not os.path.exists(os.path.join(base, local)):
                fails.append("%s: relative link '%s' does not exist" % (path, target))
        for url in BARE_URL_RE.findall(text):
            external.setdefault(url.rstrip("."), []).append(path)

    print("scanned %d file(s); %d distinct external URL(s)" % (len(set(files)), len(external)))
    if len(external) > MAX_URLS:
        fails.append(
            "%d external URLs exceeds the cap of %d; refusing to fetch. Raise MAX_URLS "
            "deliberately if the repo really grew this much." % (len(external), MAX_URLS)
        )
        offline = True
    if not offline:
        for url in sorted(external):
            error = check_url(url)
            if error:
                for path in sorted(set(external[url])):
                    fails.append("%s: %s -> %s" % (path, url, error))
    else:
        print("--offline: external URLs not fetched")

    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
