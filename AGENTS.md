# Working in this repository

This is the contributor guide for coding agents, and it is the only one — there is deliberately no
`CLAUDE.md` beside it. A second copy of these rules would be a second thing to keep in sync, in a
repository whose whole problem is copies drifting apart. If your agent reads `CLAUDE.md` and not this
file, point it here.

This repository holds Agent Skills for the WhisperGraph MCP connector. Its product is **claims** about a
live server, so the working rules below exist to stop a claim going quietly false.

Full detail is in [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

- **Verify before you commit.** Every check runs locally with no API key:
  `python3 scripts/check_frontmatter.py skills`, `check_safety_block.py`, `check_manifests.py`,
  `check_no_counts.py`, `check_links.py`, `check_surface.py`, `check_cypher.py skills`.
- **Only the six Agent Skills specification frontmatter fields.** Anything else is a hard rejection on
  claude.ai upload and the Skills API. Version lives in `plugin.json`.
- **No graph statistics in prose.** If the server can return it, teach the model to ask for it.
- **Each skill is self-contained.** No relative link leaves its own directory; references stay one level
  deep.
- **The untrusted-data block is byte-identical in all four skills.** Change it in one, change it in all,
  in the same commit.
- **Never make it easier to read an empty result as a clean one.** That is the defect this repository
  exists to prevent.
- New Cypher goes in a ```` ```cypher ```` block so CI plans it against the live graph; a deliberately
  wrong example goes in ```` ```cypher-illustrative ````.

`skills/` is the single source of truth. Nothing in this repository is generated, and there is no build
step.
