# Contributing

The product of this repository is **claims**. Almost every line asserts something about a live server:
that a tool exists, that a workflow slug is real, that an edge points a particular way, that a query
plans. A claim that goes false does not fail loudly — the model simply starts telling someone something
untrue. So the checks below are not ceremony; they are the only thing standing between a merged pull
request and a quietly wrong playbook.

## Verify before you open a pull request

Everything CI runs, you can run. **No API key and no account are needed for any of it.**

```bash
python3 scripts/check_frontmatter.py skills                   # offline
python3 scripts/check_safety_block.py skills agents           # offline
python3 scripts/check_manifests.py                            # offline
python3 scripts/check_no_counts.py skills agents commands     # offline
python3 scripts/check_links.py --offline .                    # offline

python3 scripts/check_surface.py                              # public endpoints, no key
python3 scripts/check_cypher.py skills                        # public endpoints, no key
python3 scripts/check_links.py .                              # public endpoints, no key
```

Python 3.8 or later. No third-party packages — the validators are vendored here on purpose, so that
running them never means trusting a dependency this repository does not control.

The live checks exit `0` clean, `1` on a real mismatch, and `2` when the endpoint could not be reached.
A `2` is inconclusive: an outage or a rate limit, never a reason to change a skill. They make one
anonymous request per Cypher block against a rate-limited public tier and pace themselves, so run them
once before you push rather than in a loop.

`check_links.py` fetches every external URL it finds. It refuses to contact a non-public address and
caps the number of requests, but it is still a fetcher pointed at whatever the tree names — read a
branch before you run it on one.

## The rules a change has to survive

**Only the six Agent Skills specification fields.** `name`, `description`, `license`, `compatibility`,
`metadata`, `allowed-tools`. Any other frontmatter key loads fine in Claude Code and is a **hard
rejection** on claude.ai upload and through the Skills API — which would quietly make these skills
Claude-Code-only. Version lives in `plugin.json`, never in frontmatter.

**No Claude Code-only body syntax.** No `$ARGUMENTS`, no `${CLAUDE_*}` substitution, no backtick command
injection. Same reason.

**No graph statistics in prose.** Node counts, edge counts, feed counts, label counts, rule counts, step
counts. If the server can return it, do not write it down — teach the model to ask. If you genuinely
need a number in a line, put `<!-- counts-ok: reason -->` on that line and expect to justify it in
review.

**Every skill is self-contained.** A user may install one skill and not the others. No relative link may
leave a skill's own directory, and reference files stay one level deep.

**The untrusted-data block is byte-identical everywhere.** It is duplicated across all four skills on
purpose, because each is installed independently. A change to it is a change to all four, in the same
pull request. `check_safety_block.py` enforces this and compares hashes.

**Never say "clean".** The single most important behaviour in this repository is that an indicator the
graph has never observed is never reported as safe. If a change makes an empty result easier to read as
a clean result, it will be rejected regardless of how much else it improves.

**Slugs and tool names are named, counts are not.** A wrong slug fails loudly and CI catches it. A wrong
count fails silently and CI cannot.

## Adding or changing a skill

- The directory name must equal the `name` field, in lowercase with single hyphens.
- Write the `description` in the third person, say both what it does and when to use it, and load it
  with the words a user would actually type. It is the only thing loaded into context for a skill that
  is not active, and it is what decides whether the skill fires at all. Budget it accordingly.
- Keep the body under five hundred lines and reach for `references/` before it gets there.
- New Cypher goes in a fenced ```` ```cypher ```` block so CI plans it against the live graph. A block
  that is deliberately wrong — shown to be recognised, not run — is fenced
  ```` ```cypher-illustrative ````.
- A new skill costs every user a small always-on context budget whether it fires or not. Adding one
  should replace guesswork, not restate a workflow that `list_workflows` already describes live.

## Versioning

`version` is set in `.claude-plugin/plugin.json` and in `plugin.json`, and nowhere else. The marketplace
entry deliberately carries no version: the plugin manifest wins at install time, so a second copy could
only ever disagree. `check_manifests.py` enforces both halves.

- **MAJOR** — a skill is removed or renamed, a documented install path changes, or the connector removed
  a tool a skill names. A removed tool is a major release on the day it is noticed, not a patch later.
- **MINOR** — a skill is added, or a playbook changes because the connector's surface changed.
- **PATCH** — prose, a corrected pattern, a link fix.

Every release notes the date its content was last verified against the live server. Do not claim
compatibility with a server version nobody queried.

## If the nightly drift check opens an issue

It means the server moved and something here is now false. Fix the skill. Do not add a suppression to
`scripts/check_surface.py` to make the red go away — every entry in that suppression list is a
deliberate exception, needs a comment saying why, and should draw a second reviewer.

## Reporting a problem

Wrong or misleading guidance in a skill is the highest-priority bug in this repository, above missing
features. Open an issue with the question you asked, what the assistant did, and what it should have
done.

For a problem with the graph's *data* rather than with a skill — a false positive, a wrong attribution —
the connector has a feedback tool, and support is at
[support@whisper.security](mailto:support@whisper.security).

Security issues: see [SECURITY.md](SECURITY.md). Do not open a public issue for one.
