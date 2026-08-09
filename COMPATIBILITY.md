# Compatibility

## What these skills claim

They name **tools**, not versions.

There is deliberately no supported-server-version range here. The connector versions independently, on
its own schedule, and a range asserted in this repository would be a claim with no way to check it. What
is asserted instead is falsifiable: **every tool name, resource URI and workflow slug in this repository
existed on the live server the last time CI ran**, and CI runs on every pull request and every night.

If the server stops exposing something a skill names, the nightly check fails within a day and opens an
issue. Anyone can re-establish that for themselves, with no credentials:

```bash
python3 scripts/check_surface.py
python3 scripts/check_cypher.py skills
```

We do not claim forward compatibility with a server nobody has queried.

## Where the skills run

The four skills use only the six fields in the [Agent Skills specification](https://agentskills.io/specification)
and no runtime-specific body syntax, so the same files load everywhere SKILL.md is read.

| Surface | How | Notes |
|---|---|---|
| Claude Code | plugin, or copy into `~/.claude/skills/` | Also gets the subagent and the `/whisper-setup` command |
| Claude.ai | upload a zipped skill folder in Settings | Team and Enterprise admins can provision for the organisation |
| Claude Agent SDK | filesystem discovery | Skills are files; there is no registration API |
| Claude Messages API | upload through the Skills API, reference in the request | Needs the code-execution tool. **The container has no MCP access** — a skill's *instructions* can direct the outer model to call connector tools, but nothing inside the sandbox can reach them |
| Other SKILL.md runtimes | `npx skills add whisper-sec/whisper-skills` | Detects the agents you have installed and places each skill where that one looks. `~/.agents/skills/` is the emerging shared path |

Custom skills do not sync between these surfaces. Each is a separate install.

The subagent and the slash command are Claude Code components and do not exist on the other surfaces.
Everything they do is also written into the skills, so nothing is lost — a bulk run simply happens in the
main context instead of an isolated one.

## Which clients can reach the connector

The connector speaks Streamable HTTP and requires authentication; there is no anonymous mode.

- **OAuth with dynamic client registration** is the recommended path, and most clients connect with just
  the URL.
- **A static bearer key** is the fallback for clients that do not do OAuth. Claude.ai and Claude
  Desktop's connector UI do not accept custom headers, so those two need the OAuth flow or a local
  bridge.
- **Local-transport-only clients** can use the standard remote bridge.

Per-client configuration is in the [setup guide](https://www.whisper.security/docs/ai/mcp/setup).

## Operating systems

Nothing here is platform-specific. There are no symlinks in this repository — a checkout behaves
identically on Windows, macOS and Linux, and a zip of a skill folder is valid on all three. Reference
links use forward slashes.

The validation scripts need Python 3.8 or later and no third-party packages. They are development
tooling; no skill invokes them.

## Requirements

- The WhisperGraph MCP connector at `https://mcp.whisper.security`, and an account to sign in with.
- Nothing else. No local runtime, no packages, no filesystem access, no network access beyond whatever
  your client already uses to reach the connector.
