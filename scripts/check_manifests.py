#!/usr/bin/env python3
"""Validate the plugin and marketplace manifests, and keep their versions in agreement.

Two manifests describe this repo: the Claude Code plugin manifest and the cross-vendor
Agent Plugins manifest. A version declared in two places is a version that will disagree,
so the version is set in both manifests and this check is what keeps them equal.

The Agent Plugins manifest also carries the ChatGPT and Codex listing (extensions.com.openai),
and mcp.json declares the connector for those clients. Both are held to OpenAI's
public-submission limits here, because an upload accepts drafts that a submission refuses.

Offline. No network, no credentials.

Usage:  python3 scripts/check_manifests.py
"""
import json
import os
import re
import struct
import sys

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
    if not isinstance(url, str) or not url.startswith("https://"):
        fails.append("%s.url must be an https URL" % where)
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
    return "server '%s' at %s" % (server_name, url)


def check_openai(agent, fails):
    """Hold the ChatGPT and Codex listing in plugin.json to OpenAI's public-submission limits."""
    openai = (agent.get("extensions") or {}).get("com.openai")
    if not isinstance(openai, dict):
        fails.append("%s: extensions.com.openai is missing; the ChatGPT and Codex listing lives "
                     "there" % AGENT_PLUGIN)
        return None
    for key in ("apps", "hooks"):
        if key in openai:
            fails.append("%s: extensions.com.openai.%s makes the package ineligible for the "
                         "public plugin directory" % (AGENT_PLUGIN, key))
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
    if not isinstance(listing, dict):
        fails.append("%s: extensions.com.openai.interface is missing" % AGENT_PLUGIN)
        return None
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
        if not isinstance(value, str) or not value.startswith("https://") or len(value) > 1024:
            fails.append("%s.%s must be an https URL of at most 1024 characters" % (where, field))
        elif "@" in value.split("/")[2]:
            fails.append("%s.%s must not carry credentials" % (where, field))
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

    connector = check_mcp(fails)
    return "listing '%s'; connector %s" % (listing.get("displayName"), connector or "invalid")


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
