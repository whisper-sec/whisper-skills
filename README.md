<p align="center">
  <img src="whisper-logo-512.png" alt="Whisper Security" width="120" height="120">
</p>

<h1 align="center">WhisperGraph Skills</h1>

<p align="center">
  Agent Skills for the WhisperGraph MCP server - the internet's infrastructure graph.
</p>

<p align="center">
  <a href="https://www.whisper.security/docs/whisper-graph-intro">What is WhisperGraph?</a> ·
  <a href="https://www.whisper.security/docs/mcp/setup">MCP setup</a> ·
  <a href="https://www.whisper.security/docs/mcp/reference">MCP reference</a> ·
  <a href="https://www.whisper.security/">whisper.security</a>
</p>

---

WhisperGraph is the internet's infrastructure graph - 7.4B nodes, 39B edges, and 5.6M threat-intel edges spanning DNS, BGP, WHOIS, web hyperlinks, email infrastructure, and threat feeds. The WhisperGraph MCP server gives your agent *access* to it.

These skills give the agent the *workflows*: which tool to reach for, in what order, the real schema, and the query patterns that return in milliseconds instead of timing out on billion-node labels.

## Prerequisite

The WhisperGraph MCP server must be configured in your MCP client using the **MCP setup** guide linked above. The skills reference its tools: `query`, `explain_indicator`, `whisper_history`, `domain_variants`, `list_labels`, and `describe_label`.

## Skills in this repository

| Skill | What it does | When it triggers |
|-------|--------------|------------------|
| [`whisper-investigate`](whisper-investigate/) | Threat triage and IOC enrichment. Chains `explain_indicator` → `whisper_history` → `query` pivots in the right order. | "Is this IP/domain malicious?", "investigate this indicator", "who is behind this domain?", "pivot from this IOC" |
| [`whisper-cypher`](whisper-cypher/) | Efficient Cypher authoring. Bundles the full schema, a validated cookbook by analyst persona, and the server's 7 validation rules. | "query the graph", "write Cypher for WhisperGraph", "my query was rejected / timed out", "what edge direction do I use?" |
| [`whisper-brand-protection`](whisper-brand-protection/) | Typosquatting and brand-protection sweeps. Generates lookalikes, screens for weaponization, pivots to the registrant, formats a report. | "find typosquats of my brand", "what domains impersonate us?", "brand protection sweep", "takedown prep" |

## Installation

**Web app** - zip a skill folder and upload it under Settings → Capabilities → Skills.

**Agent CLI** - copy a skill folder into your CLI's user-level skills directory, or the project's skills directory.

**API** - add the skill folder to a Messages API request via the `container.skills` parameter (requires the Code Execution Tool beta).

Each skill folder is self-contained - copy whichever ones you need.

## Quick start

1. Connect the WhisperGraph MCP server to your client.
2. Install one or more skills above.
3. Ask a natural-language question - for example *"Is 185.220.101.1 malicious?"* or *"Find typosquats of paypal.com"*. The relevant skill loads automatically.

## License

MIT - see [LICENSE](LICENSE).
