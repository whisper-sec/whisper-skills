#!/usr/bin/env python3
"""Validate the plugin and marketplace manifests, and keep their versions in agreement.

Two manifests describe this repo: the Claude Code plugin manifest and the cross-vendor
Agent Plugins manifest. A version declared in two places is a version that will disagree,
so the version is set in both manifests and this check is what keeps them equal.

Offline. No network, no credentials.

Usage:  python3 scripts/check_manifests.py
"""
import json
import os
import re
import sys

CLAUDE_PLUGIN = ".claude-plugin/plugin.json"
CLAUDE_MARKETPLACE = ".claude-plugin/marketplace.json"
AGENT_PLUGIN = "plugin.json"

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")

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

    print("plugin '%s' version %s; marketplace '%s' with %d entry/entries"
          % (name, version, market_name, len(entries)))
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
