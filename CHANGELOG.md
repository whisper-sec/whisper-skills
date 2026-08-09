# Changelog

Notable changes to the WhisperGraph skills. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [semantic versioning](https://semver.org/spec/v2.0.0.html) as defined in
[CONTRIBUTING.md](CONTRIBUTING.md).

A changelog matters more here than in most repositories: once the plugin is listed, updates reach
installed users without them asking, and this is the only place they can see what changed in the
instructions their assistant is following.

## [2.0.0] — unreleased

Everything in the previous release was written against a tool surface that no longer exists. This is a
rewrite, not an edit.

### Breaking

- **Skills moved from the repository root into `skills/`.** The documented copy command changes from
  `cp -r whisper-skills/whisper-* ~/.claude/skills/` to copying out of `skills/`, and
  `npx skills add whisper-sec/whisper-skills` now does it for you on any client.
- **Removed four tool names that no longer exist on the connector.** The skills previously instructed
  the assistant to call a history tool, a domain-variants tool, and two schema-introspection tools. All
  four are gone; the current surface answers the same questions through the schema tool, the workflow
  gallery, and procedures called inside a query. A first run against the old skills failed.
- **Removed `scripts/format_sweep.py`.** It hand-rolled what a single gallery workflow now does
  server-side, and it imposed a Python runtime requirement that no client enforces and several do not
  satisfy. Report formatting moved into the skill body.
- **Removed the sixty-pattern cookbook and the bundled schema dump.** Both were snapshots of a moving
  target and neither was tested. Replaced by a maintained pattern set that CI plans against the live
  graph on every change, and by an instruction to read the schema live.

### Added

- `whisper-bulk-triage` — a fourth skill for a list from a SIEM, EDR or spreadsheet. Splits results into
  assessed, never-seen and check-failed so an unobserved indicator is never counted as clean.
- A Claude Code subagent of the same name, so a large run happens in an isolated context and returns
  only the table.
- `/whisper-setup` — connects the connector, or works out why it is not answering.
- Plugin packaging: a Claude Code plugin manifest and marketplace entry, plus an Agent Plugins 1.0.0
  manifest for cross-vendor plugin surfaces.
- Coverage semantics throughout. Every skill now reads the coverage fields before reporting a verdict,
  and states plainly that "never seen" is not "clean".
- An identical untrusted-data block in every skill, with a check that fails the build if the copies
  drift apart.
- CI that runs with **no credentials**, so a fork's pull request gets the same verdict a maintainer's
  does: frontmatter validation against the Agent Skills specification, a live check that every tool
  name, resource and workflow slug still exists, a live check that every Cypher block still plans, a
  lint that forbids graph statistics in prose, link checking, and manifest agreement.
- A nightly drift job that opens an issue when the live surface stops matching the repository.

### Changed

- All three surviving skills rewritten against the current connector: the workflow gallery, the schema
  tool, host identity, documentation on demand, the typed error model, the self-correction contract,
  pagination and parameter binding.
- Corrected three claims that were repeated from the documentation and turned out to be wrong when
  measured against the live graph, all three of which would have made an assistant misread a result:
  a variable-length pattern **does** follow a query-time edge and return rows; the threat-listing edge
  carries **no** properties, so recency comes from a verdict's `sources[]` rather than from Cypher; and
  a verdict row can arrive with no coverage qualification at all, or with a zero score alongside a
  populated `recoveredScore` — both of which now have explicit handling rather than being read as clean.
- `whisper-brand-protection` now runs the gallery's typosquat workflow instead of a five-step hand-rolled
  sweep, and separates registered from weaponised so a defensive registration is never reported as an
  attack.
- Frontmatter reduced to the six fields in the Agent Skills specification. A runtime-specific field
  loads in Claude Code but is rejected outright by claude.ai upload and the Skills API, which would have
  quietly made these Claude-Code-only.
- Every reference to a graph statistic removed from prose, and a lint added to keep it that way.

## [1.0.0] — 2026-05-14

Initial release: three skills for threat investigation, Cypher authoring, and brand protection.
