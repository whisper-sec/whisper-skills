#!/usr/bin/env python3
"""Validate the plugin and marketplace manifests, and keep their versions in agreement.

Two manifests describe this repo: the Claude Code plugin manifest and the cross-vendor
Agent Plugins manifest. A version declared in two places is a version that will disagree,
so the version is set in both manifests and this check is what keeps them equal.

The Agent Plugins manifest also carries the ChatGPT and Codex listing, review cases and
release notes (extensions.com.openai), mcp.json declares the connector for those clients, and
each skill declares its dependency on that connector in agents/openai.yaml. All of it is held
to OpenAI's public-submission limits here, because an upload accepts drafts that a submission
refuses.

Offline. No network, no credentials.

Usage:  python3 scripts/check_manifests.py
"""
import json
import os
import re
import struct
import sys
from urllib.parse import urlsplit

CLAUDE_PLUGIN = ".claude-plugin/plugin.json"
CLAUDE_MARKETPLACE = ".claude-plugin/marketplace.json"
AGENT_PLUGIN = "plugin.json"
AGENT_MCP = "mcp.json"
AGENT_MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
MENTION = re.compile(r"(?:^|\s)@\w")

# OpenAI's limits for a public listing: "Manifest fields" in
# https://developers.openai.com/plugins/deploy/submission (read 2026-11-22).
LISTING_TEXT = (
    ("displayName", 30),
    ("shortDescription", 30),
    ("longDescription", 4000),
    ("developerName", 80),
    ("category", None),  # a category title from the dashboard; no stated length
)
LISTING_URLS = ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL")
LISTING_ICONS = ("logo", "composerIcon", "logoDark", "composerIconDark")
REQUIRED_ICONS = ("logo", "composerIcon")
ICON_FORMATS = (".png", ".jpg", ".jpeg", ".webp", ".svg")
ICON_MAX_BYTES = 5 * 1024 * 1024
# The color must keep 2:1 contrast against the theme background it is shown on.
BRAND_COLORS = (("brandColor", "#FFFFFF"), ("brandColorDark", "#212121"))

# "Configure onboarding, review, and publication" in the same page (read 2026-11-23). Initial
# review of a plugin with an MCP server needs exactly five positive and three negative cases.
OPENAI_KEYS = {"interface", "onboardingSkill", "review", "publication"}
REVIEW_KEYS = {"test_cases", "demo_recording_url", "commerce", "commerce_description"}
CASE_KEYS = {"description", "prompt", "tools_triggered", "expected_behavior",
             "file_attachment_urls", "expected_output_url"}
CASE_COUNTS = (("positive", 5), ("negative", 3))
PUBLICATION_KEYS = {"countries", "release_notes", "translations"}
COUNTRY = re.compile(r"^[A-Z]{2}$")

# "Use MCP tools from a skill" in https://developers.openai.com/plugins/build/skills.
SKILLS_DIR = "skills"
SKILL_DEPENDENCY = os.path.join("agents", "openai.yaml")
YAML_KEY = re.compile(r"^(\s*)(-\s+)?([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*))?$")

# Reserved by Anthropic; a marketplace using one of these will not load.
RESERVED_MARKETPLACE_NAMES = {
    "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
    "claude-plugins-community", "claude-community", "anthropic-marketplace",
    "anthropic-plugins", "agent-skills", "anthropic-agent-skills",
    "knowledge-work-plugins", "life-sciences", "claude-for-legal",
    "claude-for-financial-services", "financial-services-plugins",
    "first-party-plugins", "healthcare", "org", "org-provisioned", "unknown",
}


def load(path, fails):
    if not os.path.exists(path):
        fails.append("%s: missing" % path)
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except ValueError as exc:
        fails.append("%s: invalid JSON — %s" % (path, exc))
        return None


def luminance(color):
    """WCAG relative luminance of a #RRGGBB color."""
    def channel(value):
        value /= 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def icon_size(path):
    """(width, height) of a PNG or SVG icon, or None for a format this check does not read."""
    with open(path, "rb") as handle:
        head = handle.read(32)
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return struct.unpack(">II", head[16:24])
    if path.lower().endswith(".svg"):
        text = open(path, encoding="utf-8", errors="replace").read()
        box = re.search(r'viewBox\s*=\s*"\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*"', text)
        if box:
            return float(box.group(1)), float(box.group(2))
        width = re.search(r'<svg\b[^>]*\swidth\s*=\s*"([\d.]+)(?:px)?"', text)
        height = re.search(r'<svg\b[^>]*\sheight\s*=\s*"([\d.]+)(?:px)?"', text)
        if width and height:
            return float(width.group(1)), float(height.group(1))
    return None


def check_icon(field, path, fails):
    where = "%s: extensions.com.openai.interface.%s" % (AGENT_PLUGIN, field)
    if not isinstance(path, str) or not path.startswith("./") or ".." in path:
        fails.append("%s must be a ./ path inside the repo, not %r" % (where, path))
        return
    if not os.path.isfile(path):
        fails.append("%s: %s does not exist" % (where, path))
        return
    extension = os.path.splitext(path)[1].lower()
    if extension not in ICON_FORMATS:
        fails.append("%s: %s is not PNG, JPEG, WebP or SVG" % (where, path))
        return
    if os.path.getsize(path) > ICON_MAX_BYTES:
        fails.append("%s: %s is over 5 MiB" % (where, path))
    size = icon_size(path)
    if size is None:
        fails.append("%s: cannot read the size of %s; use PNG or SVG, or teach icon_size() "
                     "the format" % (where, path))
        return
    width, height = size
    if width != height:
        fails.append("%s: %s is %gx%g, not square" % (where, path, width, height))
    if min(width, height) < 48:
        fails.append("%s: %s is under 48 px" % (where, path))
    if extension != ".svg" and max(width, height) > 4096:
        fails.append("%s: %s is over 4096 px" % (where, path))


def has_key(value, key):
    """True when key appears anywhere inside a parsed JSON value."""
    if isinstance(value, dict):
        return key in value or any(has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(has_key(v, key) for v in value)
    return False


def check_mcp(fails):
    """The connector for ChatGPT and Codex: one remote server, OAuth, nothing secret."""
    mcp = load(AGENT_MCP, fails)
    if mcp is None:
        return None
    if mcp.get("$schema") != AGENT_MCP_SCHEMA:
        fails.append("%s: $schema must be the Agent Plugins 1.0.0 MCP schema" % AGENT_MCP)
    if has_key(mcp, "clientSecret"):
        fails.append("%s: clientSecret is rejected by the manifest, and this repository is public"
                     % AGENT_MCP)
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict) or len(servers) != 1:
        fails.append("%s: mcpServers must declare exactly one server; plugin-level review cases "
                     "need exactly one" % AGENT_MCP)
        return None
    (server_name, server), = servers.items()
    where = "%s: mcpServers.%s" % (AGENT_MCP, server_name)
    if not isinstance(server, dict):
        fails.append("%s must be an object" % where)
        return None
    if not KEBAB.match(server_name):
        fails.append("%s: the server name should be kebab-case" % where)
    if server.get("type") != "streamable-http":
        fails.append("%s.type must be streamable-http; the connector speaks Streamable HTTP" % where)
    url = server.get("url")
    if not is_https(url):
        fails.append("%s.url must be an https URL with a host and no credentials" % where)
    if server.get("headers"):
        fails.append("%s.headers must be empty; public submission rejects server headers" % where)
    if "command" in server:
        fails.append("%s.command declares a local server; the directory takes a remote endpoint"
                     % where)
    auth = ((server.get("extensions") or {}).get("com.openai") or {}).get("auth") or {}
    if auth.get("type") != "oauth":
        fails.append("%s.extensions.com.openai.auth.type must be oauth; the connector has no "
                     "anonymous mode" % where)
    client = auth.get("client")
    if client is not None:
        mode = client.get("mode") if isinstance(client, dict) else None
        if mode not in ("provided", "dcr", "cimd"):
            fails.append("%s: auth.client.mode must be provided, dcr or cimd" % where)
        elif mode != "provided" and ("clientId" in client or "tokenEndpointAuthMethod" in client):
            fails.append("%s: a %s client takes no clientId or tokenEndpointAuthMethod"
                         % (where, mode))
    return server_name, url


def is_https(value):
    """An https URL with a host and no credentials in it."""
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme == "https" and bool(parts.hostname) and "@" not in parts.netloc


def check_review(review, fails):
    """The review cases and commerce declaration, as the dashboard imports them from the ZIP."""
    where = "%s: extensions.com.openai.review" % AGENT_PLUGIN
    if not isinstance(review, dict):
        fails.append("%s is missing; a plugin with an MCP server needs review cases for its first "
                     "review" % where)
        return 0, 0
    for key in sorted(set(review) - REVIEW_KEYS - {"test_credentials", "reviewer_instructions"}):
        fails.append("%s.%s is not a review field" % (where, key))
    if "demo_recording_url" in review and not is_https(review["demo_recording_url"]):
        fails.append("%s.demo_recording_url must be an https URL" % where)
    if "commerce" in review and not isinstance(review["commerce"], bool):
        fails.append("%s.commerce must be true or false" % where)
    if "commerce_description" in review and (
            not isinstance(review["commerce_description"], str)
            or not review["commerce_description"].strip()):
        fails.append("%s.commerce_description must be non-empty text" % where)

    cases = review.get("test_cases")
    if not isinstance(cases, dict):
        fails.append("%s.test_cases must hold the positive and negative cases" % where)
        return 0, 0
    counts = []
    for kind, required in CASE_COUNTS:
        entries = cases.get(kind)
        if not isinstance(entries, list) or len(entries) != required:
            fails.append("%s.test_cases.%s must hold exactly %d cases, not %s"
                         % (where, kind, required,
                            len(entries) if isinstance(entries, list) else "none"))
            counts.append(0)
            continue
        counts.append(len(entries))
        prompts = []
        for i, case in enumerate(entries):
            at = "%s.test_cases.%s[%d]" % (where, kind, i)
            if not isinstance(case, dict):
                fails.append("%s must be an object" % at)
                continue
            for key in sorted(set(case) - CASE_KEYS):
                fails.append("%s.%s is not a test-case field" % (at, key))
            needed = ("description", "prompt")
            if kind == "positive":
                needed += ("tools_triggered", "expected_behavior")
            for key in needed:
                if not isinstance(case.get(key), str) or not case[key].strip():
                    fails.append("%s.%s is required" % (at, key))
            description = case.get("description")
            if kind == "positive" and isinstance(description, str) and len(description) > 4000:
                fails.append("%s.description is over 4000 characters" % at)
            urls = case.get("file_attachment_urls", [])
            if not isinstance(urls, list) or not all(is_https(u) for u in urls):
                fails.append("%s.file_attachment_urls must be a list of https URLs" % at)
            if "expected_output_url" in case and not is_https(case["expected_output_url"]):
                fails.append("%s.expected_output_url must be an https URL" % at)
            if isinstance(case.get("prompt"), str):
                prompts.append(case["prompt"].strip())
        if len(set(prompts)) != len(prompts):
            fails.append("%s.test_cases.%s repeats a prompt" % (where, kind))
    return tuple(counts)


def check_publication(publication, fails):
    where = "%s: extensions.com.openai.publication" % AGENT_PLUGIN
    if publication is None:
        return
    if not isinstance(publication, dict):
        fails.append("%s must be an object" % where)
        return
    for key in sorted(set(publication) - PUBLICATION_KEYS):
        fails.append("%s.%s is not a publication field" % (where, key))
    notes = publication.get("release_notes")
    if notes is not None and (not isinstance(notes, str) or not notes.strip()):
        fails.append("%s.release_notes must be non-empty text" % where)
    countries = publication.get("countries")
    if countries is not None and (not isinstance(countries, list)
                                  or not all(isinstance(c, str) and COUNTRY.match(c)
                                             for c in countries)):
        fails.append("%s.countries must be a list of uppercase two-letter country codes" % where)
    translations = publication.get("translations")
    if translations is None:
        return
    if not isinstance(translations, dict):
        fails.append("%s.translations must map locales to listing text" % where)
        return
    for locale, text in translations.items():
        if not isinstance(text, dict):
            fails.append("%s.translations.%s must be an object" % (where, locale))
            continue
        for field, limit in (("subtitle", 30), ("description", 4000)):
            value = text.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                fails.append("%s.translations.%s.%s must be text of at most %d characters"
                             % (where, locale, field, limit))


def yaml_scalar(text, number):
    """One YAML scalar and any comment after it: the value, or None when the line has none.

    Reads the quoted and plain one-line forms. A # starts a comment only outside quotes and
    after whitespace, so a color such as "#8A5CC7" or a quoted " # " stays part of its value.
    """
    text = (text or "").strip()
    if not text or text.startswith("#"):
        return None
    if text[0] in "|>":
        raise ValueError("line %d: a block scalar is not read here; write the value on one line"
                         % number)
    if text[0] not in "\"'":
        cut = re.search(r"\s#", text)
        return text[:cut.start()].rstrip() if cut else text
    quote, out, i = text[0], [], 1
    while i < len(text):
        ch = text[i]
        if quote == '"' and ch == "\\":
            if text[i + 1:i + 2] not in ('"', "\\"):
                raise ValueError("line %d: an escape other than \\\" or \\\\ is not read here"
                                 % number)
            out.append(text[i + 1])
            i += 2
            continue
        if ch == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            rest = text[i + 1:].strip()
            if rest and not rest.startswith("#"):
                raise ValueError("line %d: text after the closing quote" % number)
            return "".join(out)
        out.append(ch)
        i += 1
    raise ValueError("line %d: the quoted value is not closed" % number)


def read_dependency(path):
    """The tool dependencies in a skill's agents/openai.yaml, as a list of dicts.

    A deliberately small reader, so the check needs no third-party YAML parser. It reads the
    top-level dependencies block, where tools is a list of flat key: value entries, and passes
    over every other section, such as interface and policy, unread.
    """
    tools, top, sub, sub_indent, current = [], None, None, None, None
    for number, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.rstrip()
        text = line.lstrip()
        if not text or text.startswith("#") or text in ("---", "..."):
            continue
        indent = len(line) - len(text)
        listed = text == "-" or text.startswith("- ")
        if indent == 0 and not listed:
            match = YAML_KEY.match(line)
            if not match:
                raise ValueError("line %d is not a top-level key" % number)
            top, sub, sub_indent, current = match.group(3), None, None, None
            if top == "dependencies" and yaml_scalar(match.group(4), number) is not None:
                raise ValueError("line %d: dependencies must be a mapping" % number)
            continue
        if top != "dependencies":
            continue
        if sub_indent is None:
            sub_indent = indent
        if indent < sub_indent:
            raise ValueError("line %d is indented less than the block it is in" % number)
        if indent == sub_indent and not listed:
            match = YAML_KEY.match(line)
            if not match:
                raise ValueError("line %d is not a key: value pair" % number)
            sub, current = match.group(3), None
            if sub == "tools" and yaml_scalar(match.group(4), number) is not None:
                raise ValueError("line %d: dependencies.tools must be a list of entries" % number)
            continue
        if sub != "tools":
            continue
        match = YAML_KEY.match(line)
        if not match:
            raise ValueError("line %d is not a key: value pair" % number)
        key, value = match.group(3), yaml_scalar(match.group(4), number)
        if match.group(2):
            current = {}
            tools.append(current)
        elif current is None:
            raise ValueError("line %d: '%s' is not inside a dependencies.tools entry" % (number, key))
        if value is None:
            raise ValueError("line %d: '%s' has no value; a tool entry holds flat key: value pairs"
                             % (number, key))
        current[key] = value
    return tools


def check_skill_dependencies(server, fails):
    """Every skill names the connector it needs, and names it exactly as mcp.json declares it."""
    names = sorted(d for d in os.listdir(SKILLS_DIR)
                   if os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md")))
    for name in names:
        path = os.path.join(SKILLS_DIR, name, SKILL_DEPENDENCY)
        if not os.path.isfile(path):
            fails.append("%s: missing; declare the connector this skill calls" % path)
            continue
        try:
            tools = read_dependency(path)
        except ValueError as exc:
            fails.append("%s: %s" % (path, exc))
            continue
        mcp = [t for t in tools if t.get("type") == "mcp"]
        if len(mcp) != 1:
            fails.append("%s: declare exactly one mcp tool dependency, not %d" % (path, len(mcp)))
            continue
        entry = mcp[0]
        if server is not None:
            server_name, url = server
            if entry.get("value") != server_name:
                fails.append("%s: value '%s' is not the server '%s' in %s"
                             % (path, entry.get("value"), server_name, AGENT_MCP))
            if entry.get("url") != url:
                fails.append("%s: url '%s' is not %s's %s" % (path, entry.get("url"), AGENT_MCP, url))
        if entry.get("transport") != "streamable_http":
            fails.append("%s: transport must be streamable_http" % path)
        if not (entry.get("description") or "").strip():
            fails.append("%s: description is required" % path)
    return len(names)


def check_openai(agent, fails):
    """Hold the ChatGPT and Codex listing in plugin.json to OpenAI's public-submission limits."""
    openai = (agent.get("extensions") or {}).get("com.openai")
    if not isinstance(openai, dict):
        fails.append("%s: extensions.com.openai is missing; the ChatGPT and Codex listing lives "
                     "there" % AGENT_PLUGIN)
        openai = {}
    for key in ("apps", "hooks"):
        if key in openai:
            fails.append("%s: extensions.com.openai.%s makes the package ineligible for the "
                         "public plugin directory" % (AGENT_PLUGIN, key))
    for key in sorted(set(openai) - OPENAI_KEYS - {"apps", "hooks"}):
        fails.append("%s: extensions.com.openai.%s is not an OpenAI plugin field"
                     % (AGENT_PLUGIN, key))
    onboarding = openai.get("onboardingSkill")
    if onboarding is not None and (
            not isinstance(onboarding, str) or not onboarding.startswith("./skills/")
            or not onboarding.endswith("/SKILL.md") or ".." in onboarding
            or not os.path.isfile(onboarding)):
        fails.append("%s: extensions.com.openai.onboardingSkill must be the ./skills/<name>/SKILL.md "
                     "of a packaged skill" % AGENT_PLUGIN)
    for path in ("hooks/hooks.json", ".app.json"):
        if os.path.exists(path):
            fails.append("%s exists; a package with lifecycle hooks or app references cannot be "
                         "submitted to the public plugin directory" % path)
    review = openai.get("review")
    if isinstance(review, dict):
        for key in ("test_credentials", "reviewer_instructions"):
            if key in review:
                fails.append("%s: extensions.com.openai.review.%s is rejected by the upload; "
                             "reviewer access goes in the dashboard, never in this public "
                             "repository" % (AGENT_PLUGIN, key))

    listing = openai.get("interface")
    if isinstance(listing, dict):
        check_listing(listing, fails)
    else:
        fails.append("%s: extensions.com.openai.interface is missing" % AGENT_PLUGIN)
        listing = {}

    server = check_mcp(fails)
    positive, negative = check_review(review, fails)
    check_publication(openai.get("publication"), fails)
    skills = check_skill_dependencies(server, fails)
    return "listing '%s'; connector %s; review cases %d positive, %d negative; dependency files checked for %d skills" % (
        listing.get("displayName"),
        "'%s' at %s" % server if server else "invalid",
        positive, negative, skills)


def check_listing(listing, fails):
    """The directory listing text, links, prompts, colors and icons."""
    where = "%s: extensions.com.openai.interface" % AGENT_PLUGIN
    for field, limit in LISTING_TEXT:
        value = listing.get(field)
        if not isinstance(value, str) or not value.strip():
            fails.append("%s.%s is required" % (where, field))
        elif limit and len(value) > limit:
            fails.append("%s.%s is %d characters; the limit is %d"
                         % (where, field, len(value), limit))
    capabilities = listing.get("capabilities", [])
    if not isinstance(capabilities, list) or len(capabilities) > 20 or any(
            not isinstance(c, str) or not c.strip() or len(c) > 120 for c in capabilities):
        fails.append("%s.capabilities must be at most 20 labels of at most 120 characters" % where)
    for field in LISTING_URLS:
        value = listing.get(field)
        if not is_https(value) or len(value) > 1024:
            fails.append("%s.%s must be an https URL with a host and no credentials, of at most "
                         "1024 characters" % (where, field))
    prompts = listing.get("defaultPrompt", [])
    if isinstance(prompts, str):
        prompts = [prompts]
    if not isinstance(prompts, list) or len(prompts) > 3:
        fails.append("%s.defaultPrompt takes at most three prompts" % where)
    else:
        for prompt in prompts:
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 128:
                fails.append("%s.defaultPrompt %r must be 1 to 128 characters" % (where, prompt))
            elif MENTION.search(prompt):
                fails.append("%s.defaultPrompt %r must not @mention an app" % (where, prompt))
        if len(set(prompts)) != len(prompts):
            fails.append("%s.defaultPrompt entries must be unique" % where)
    for field, background in BRAND_COLORS:
        value = listing.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not HEX_COLOR.match(value):
            fails.append("%s.%s must be #RRGGBB" % (where, field))
        elif contrast(value, background) < 2:
            fails.append("%s.%s %s has %.2f:1 contrast against %s; the minimum is 2:1"
                         % (where, field, value, contrast(value, background), background))
    for field in REQUIRED_ICONS:
        if field not in listing:
            fails.append("%s.%s is required" % (where, field))
    for field in LISTING_ICONS:
        if field in listing:
            check_icon(field, listing[field], fails)


def main():
    fails = []
    plugin = load(CLAUDE_PLUGIN, fails)
    marketplace = load(CLAUDE_MARKETPLACE, fails)
    agent = load(AGENT_PLUGIN, fails)
    if plugin is None or marketplace is None or agent is None:
        for f in fails:
            print("FAIL", f)
        print("%d failure(s)" % len(fails))
        return 1

    name = plugin.get("name")
    if not name:
        fails.append("%s: name is required" % CLAUDE_PLUGIN)
    elif not KEBAB.match(name):
        fails.append("%s: name '%s' should be kebab-case" % (CLAUDE_PLUGIN, name))

    version = plugin.get("version")
    if not version:
        fails.append(
            "%s: version is required. Without it, version resolution falls back to the "
            "commit SHA and every push becomes a release" % CLAUDE_PLUGIN
        )
    elif not SEMVER.match(str(version)):
        fails.append("%s: version '%s' is not semver" % (CLAUDE_PLUGIN, version))

    if agent.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        fails.append("%s: $schema must be the Agent Plugins 1.0.0 plugin schema" % AGENT_PLUGIN)
    if agent.get("name") != name:
        fails.append(
            "%s: name '%s' differs from %s name '%s'"
            % (AGENT_PLUGIN, agent.get("name"), CLAUDE_PLUGIN, name)
        )
    if str(agent.get("version")) != str(version):
        fails.append(
            "%s: version '%s' differs from %s version '%s'"
            % (AGENT_PLUGIN, agent.get("version"), CLAUDE_PLUGIN, version)
        )

    market_name = marketplace.get("name")
    if not market_name:
        fails.append("%s: name is required" % CLAUDE_MARKETPLACE)
    elif market_name.lower() in RESERVED_MARKETPLACE_NAMES:
        fails.append("%s: '%s' is a reserved marketplace name" % (CLAUDE_MARKETPLACE, market_name))
    if not (marketplace.get("owner") or {}).get("name"):
        fails.append("%s: owner.name is required" % CLAUDE_MARKETPLACE)

    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or not entries:
        fails.append("%s: plugins must be a non-empty array" % CLAUDE_MARKETPLACE)
        entries = []
    for i, entry in enumerate(entries):
        if not entry.get("name"):
            fails.append("%s: plugins[%d].name is required" % (CLAUDE_MARKETPLACE, i))
        source = entry.get("source")
        if source is None:
            fails.append("%s: plugins[%d].source is required" % (CLAUDE_MARKETPLACE, i))
        elif isinstance(source, str):
            if not source.startswith("./"):
                fails.append(
                    "%s: plugins[%d].source '%s' must start with ./"
                    % (CLAUDE_MARKETPLACE, i, source)
                )
            if ".." in source:
                fails.append("%s: plugins[%d].source escapes the repo" % (CLAUDE_MARKETPLACE, i))
        if "version" in entry:
            fails.append(
                "%s: plugins[%d] declares a version. plugin.json wins at install time, so a "
                "version here can only ever disagree — remove it" % (CLAUDE_MARKETPLACE, i)
            )
        if entry.get("name") == name and entry.get("source") == "./":
            for component in ("skills", "agents", "commands"):
                path = component
                if os.path.isdir(path) and not os.listdir(path):
                    fails.append("%s/ exists but is empty" % path)

    if not any(e.get("name") == name for e in entries):
        fails.append(
            "%s: no entry names the plugin '%s'" % (CLAUDE_MARKETPLACE, name)
        )

    openai = check_openai(agent, fails)

    print("plugin '%s' version %s; marketplace '%s' with %d entry/entries"
          % (name, version, market_name, len(entries)))
    if openai:
        print("openai: %s" % openai)
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
