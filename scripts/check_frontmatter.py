#!/usr/bin/env python3
"""Validate every SKILL.md against the Agent Skills specification.

Offline. No network, no third-party dependency, no credentials.
Spec: https://agentskills.io/specification

Only the six fields in the open spec are permitted. A skill carrying a runtime-specific
field loads in Claude Code but is REJECTED OUTRIGHT by claude.ai upload and the Skills
API, so a field outside the six is an error here, not a warning.

Usage:  python3 scripts/check_frontmatter.py skills
"""
import os
import re
import sys

SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Reserved by the Anthropic platform: a skill whose name contains either is rejected on upload.
RESERVED_IN_NAME = ("anthropic", "claude")

MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_LINES = 500
MAX_BODY_TOKENS = 5000  # spec recommendation; we estimate at 4 chars/token


def parse_frontmatter(text):
    """Minimal YAML-subset frontmatter parser: scalars plus one level of nesting."""
    if not text.startswith("---\n"):
        return None, "no YAML frontmatter"
    end = text.find("\n---", 3)
    if end < 0:
        return None, "unterminated frontmatter"
    raw, body = text[4:end], text[end + 4:]
    fields, current = {}, None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\s+\S", line) and current:
            key, _, value = line.strip().partition(":")
            fields.setdefault(current, {})[key.strip()] = value.strip()
        else:
            key, _, value = line.partition(":")
            current = key.strip()
            fields[current] = value.strip() if value.strip() else {}
    return (fields, body), None


def check_skill(skill_dir):
    path = os.path.join(skill_dir, "SKILL.md")
    dirname = os.path.basename(os.path.abspath(skill_dir))
    if not os.path.exists(path):
        return ["%s: no SKILL.md" % skill_dir]

    text = open(path, encoding="utf-8").read()
    parsed, err = parse_frontmatter(text)
    if parsed is None:
        return ["%s: %s" % (path, err)]
    fields, body = parsed
    fails = []

    for key in fields:
        if key not in SPEC_FIELDS:
            fails.append(
                "%s: frontmatter key '%s' is not in the Agent Skills spec — this is a hard "
                "error on claude.ai upload and the Skills API" % (path, key)
            )

    name = fields.get("name")
    if not isinstance(name, str) or not name:
        fails.append("%s: name is required" % path)
    else:
        if len(name) > MAX_NAME:
            fails.append("%s: name is %d chars, max %d" % (path, len(name), MAX_NAME))
        if not NAME_RE.match(name):
            fails.append(
                "%s: name '%s' must be lowercase alphanumeric and hyphens, with no leading, "
                "trailing or consecutive hyphens" % (path, name)
            )
        if name != dirname:
            fails.append("%s: name '%s' must match the directory name '%s'" % (path, name, dirname))
        for word in RESERVED_IN_NAME:
            if word in name:
                fails.append("%s: name contains the reserved word '%s'" % (path, word))

    description = fields.get("description")
    if not isinstance(description, str) or not description:
        fails.append("%s: description is required" % path)
    elif len(description) > MAX_DESCRIPTION:
        fails.append("%s: description is %d chars, max %d" % (path, len(description), MAX_DESCRIPTION))
    elif re.search(r"<[a-zA-Z/][^>]*>", description):
        fails.append("%s: description must not contain XML-style tags" % path)
    elif re.match(r"^\s*(I |You |We |Let me |This skill lets you)", description):
        fails.append("%s: description must be written in the third person" % path)

    compatibility = fields.get("compatibility")
    if isinstance(compatibility, str) and len(compatibility) > MAX_COMPATIBILITY:
        fails.append(
            "%s: compatibility is %d chars, max %d" % (path, len(compatibility), MAX_COMPATIBILITY)
        )

    metadata = fields.get("metadata")
    if metadata and not isinstance(metadata, dict):
        fails.append("%s: metadata must be a map of string keys to string values" % path)

    line_count = len(text.splitlines())
    if line_count > MAX_LINES:
        fails.append("%s: %d lines; the spec recommends under %d" % (path, line_count, MAX_LINES))
    approx_tokens = len(body) // 4
    if approx_tokens > MAX_BODY_TOKENS:
        fails.append(
            "%s: body is ~%d tokens; the spec recommends under %d"
            % (path, approx_tokens, MAX_BODY_TOKENS)
        )

    # Claude Code-only body syntax breaks the skill on every other surface.
    for pattern, why in (
        (r"\$ARGUMENTS", "$ARGUMENTS is Claude Code-only"),
        (r"\$\{CLAUDE_[A-Z_]+\}", "${CLAUDE_*} substitution is Claude Code-only"),
        (r"!`", "backtick command injection is Claude Code-only"),
    ):
        if re.search(pattern, body):
            fails.append("%s: %s and does not work on claude.ai or the Skills API" % (path, why))

    for link in re.findall(r"\]\(([^)#][^)]*)\)", body):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        if "\\" in link:
            fails.append("%s: reference '%s' uses a backslash; use forward slashes" % (path, link))
        if link.startswith("../"):
            fails.append(
                "%s: reference '%s' escapes the skill directory; each skill must be "
                "self-contained" % (path, link)
            )
            continue
        if link.count("/") > 1:
            fails.append("%s: reference '%s' is more than one level deep" % (path, link))
        if not os.path.exists(os.path.join(skill_dir, link)):
            fails.append("%s: reference '%s' does not exist" % (path, link))

    return fails


def main(root):
    fails = []
    names = []
    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            names.append(entry)
            fails += check_skill(path)
    print("checked %d skill(s): %s" % (len(names), ", ".join(names) or "none"))
    for f in fails:
        print("FAIL", f)
    print("%d failure(s)" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "skills"))
