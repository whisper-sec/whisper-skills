<h1 align="center">WhisperGraph Skills</h1>

<p align="center">
  Investigation playbooks for the WhisperGraph MCP connector — for Claude Code, Claude.ai,
  and every other client that reads Agent Skills.
</p>

<p align="center">
  <a href="https://www.whisper.security/docs/ai/mcp/setup">Connect the server</a> ·
  <a href="https://www.whisper.security/docs/ai/mcp/reference">Tool reference</a> ·
  <a href="https://www.whisper.security/docs/ai/mcp/workflow-gallery">Workflow gallery</a> ·
  <a href="https://www.whisper.security">whisper.security</a>
</p>

---

WhisperGraph is an internet-infrastructure graph: DNS, BGP and RPKI, IP allocation and GeoIP, WHOIS
ownership, email authentication, certificate transparency, web links, physical backbone, and threat
feeds — pre-joined, so one traversal crosses layers that are separate products everywhere else. The
[MCP connector](https://www.whisper.security/docs/ai/mcp/setup) gives an AI assistant read access to it.

**The connector runs the investigation. These skills decide which one to run, and say what the answer
is worth.** Those are the two jobs a server cannot do for you: it never sees the question you were
actually asked, and it never sees the conclusion you are about to write. The second one matters more
than it sounds — a verdict of "not listed" and a verdict of "never seen" are the same shape in an API
response and opposite findings in an investigation, and the second one is what a domain registered this
morning looks like.

## The skills

| Skill | The job | It fires when you say |
|---|---|---|
| [`whisper-investigate`](skills/whisper-investigate/) | Triage one indicator: pick the right workflow, read the coverage, stop when the question is answered | "is this domain malicious", "who owns this IP", "map our attack surface", "can this subdomain be taken over" |
| [`whisper-bulk-triage`](skills/whisper-bulk-triage/) | A list from a SIEM, EDR or spreadsheet, ranked — with never-seen and check-failed kept out of the ranked table | "here are 200 IPs from Splunk", "which of these matter", "triage this blocklist" |
| [`whisper-cypher`](skills/whisper-cypher/) | Custom queries for the questions no workflow covers, written to pass the server's validator first time | "write a query for…", "my query was rejected", "what edge direction do I use", "why did this return nothing" |
| [`whisper-brand-protection`](skills/whisper-brand-protection/) | Lookalike domains, separated into weaponised, suspicious, and merely registered — then a takedown package | "find typosquats of our brand", "who is impersonating us", "build a takedown case" |

Each loads on its own when a question matches. There is nothing to invoke.

## Install

Everything here needs the connector. Add it first — it is one URL and a browser sign-in:
[setup guide](https://www.whisper.security/docs/ai/mcp/setup).

**Claude Code — as a plugin**

```
/plugin marketplace add whisper-sec/whisper-skills
/plugin install whisper-graph@whisper-security
```

That brings the four skills, a `whisper-bulk-triage` subagent for large lists, and a `/whisper-setup`
command that connects the server or works out why it is not answering.

**Any other agent — one command**

```
npx skills add whisper-sec/whisper-skills
```

`npx skills` detects which agents you have installed and writes the skills where each one looks for
them. Its coverage is broad and changes often — run it and it will tell you what it found.

**Claude.ai**

Zip a folder under `skills/` and upload it in Settings. Team and Enterprise administrators can provision
skills for everyone from organisation settings.

**Manually**

Copy the folders you want out of `skills/` into `~/.claude/skills/`, `~/.agents/skills/`, or wherever
your client looks. Each skill is self-contained — no skill reads a file belonging to another.

## What is here

```
skills/           four skills, the single source of truth. Agent Skills spec, six frontmatter
                  fields only, so they load unchanged in Claude Code, on claude.ai, through the
                  Skills API, and in every other SKILL.md runtime
agents/           one Claude Code subagent: bulk triage in an isolated context
commands/         /whisper-setup — connect the connector, or diagnose it
scripts/          the checks that keep this repo true. No dependencies, no credentials
plugin.json       Agent Plugins 1.0.0, for cross-vendor plugin surfaces
.claude-plugin/   the Claude Code plugin and marketplace manifests
```

## No numbers

You will not find a node count, an edge count, a feed count or a tool count written down in these
skills, and CI fails the build if one appears.

The graph ingests continuously, and the published documentation pages have disagreed with each other
about these numbers. A statistic written into a playbook is a statistic that goes wrong quietly — no
test fails, the model just starts telling people something untrue. So the rule is: **if the server can
return it, do not write it down.** Ask `explain_schema` for the labels and edges, the live statistics
resource for magnitudes, and `list_workflows` for what the gallery currently holds.

The same rule is why the previous version of this repo went stale: it named tools that had been removed
and nothing failed. Now `scripts/check_surface.py` asserts every tool name, resource URI and workflow
slug against the live server on every pull request and every night, and `scripts/check_cypher.py` plans
every query in the repo against the live graph. Both run with **no credentials**, so a fork's pull
request gets exactly the verdict a maintainer's does.

Run them yourself:

```bash
python3 scripts/check_frontmatter.py skills   # offline
python3 scripts/check_surface.py              # public endpoints, no key
python3 scripts/check_cypher.py skills        # public endpoints, no key
```

The live checks exit `0` when clean, `1` on a real mismatch, and `2` when the endpoint could not be
reached — so an outage reads as inconclusive rather than as a repository defect, and the nightly job
only files an issue on a `1`.

## Security

These skills drive a read-only surface. The two contribution tools on the connector write, and every
skill here says the same thing about them: never call one without asking first.

Rows the graph returns are strings third parties wrote, and in an investigation some of them were
written by the people under investigation. Every skill carries an identical block instructing the model
to treat returned values as inert data — never as instructions, never as a URL to fetch, never as
something to execute. `scripts/check_safety_block.py` fails the build if those copies ever drift apart.

See [SECURITY.md](SECURITY.md).

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Everything CI checks, you
can run locally with no API key and no account.

## License

MIT — see [LICENSE](LICENSE).
