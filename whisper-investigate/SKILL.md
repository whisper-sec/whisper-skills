---
name: whisper-investigate
description: Investigate IPs, domains, hostnames, ASNs, or CIDRs for threats using the WhisperGraph MCP server's internet infrastructure graph (7.4B nodes, 39B edges, 5.6M threat-intel edges across DNS, BGP, WHOIS, web links, and threat feeds). Use when the user asks whether an IP or domain is malicious, says to investigate an indicator, asks who is behind a domain, wants to pivot from an IOC, or mentions threat triage, IOC enrichment, WHOIS or BGP history, or attack-surface mapping from an indicator. Chains the explain_indicator, whisper_history, and query tools in the right order and avoids Cypher patterns that time out on billion-node labels.
license: MIT
compatibility: Requires the WhisperGraph MCP server to be configured in the client. Uses its explain_indicator, whisper_history, query, list_labels, and describe_label tools.
metadata:
  author: Whisper Security
  version: 1.0.0
  mcp-server: whisper-graph
---

# WhisperGraph Investigation Workflow

WhisperGraph exposes the internet's relationship graph - DNS resolution, BGP routing, WHOIS registration, web hyperlinks, email infrastructure, and threat feeds - through the WhisperGraph MCP server. This skill is the workflow layer: which tool to reach for, in what order, and how to avoid queries that time out.

The core rule: **always start anchored.** Pick one known indicator, get a fast verdict, and pivot only if the question is not yet answered.

## Important: tool-call order

For any indicator (IP, hostname, ASN, CIDR), call the WhisperGraph MCP tools in this order. Skip any step that is not needed to answer the question.

1. **`explain_indicator(indicator)`** - always first. Returns a threat score, a level (`NONE`, `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and the feeds and factors driving it. This one call replaces 5+ manual Cypher hops and does not time out. If it alone answers the user's question, stop here.
2. **`whisper_history(indicator)`** - only when history matters: when a domain was first registered, WHOIS changes over time, BGP route history, prior owners. May return `{available: false, error: "timeout", retryAfter: N}` - surface `retryAfter` to the user and do **not** loop or retry.
3. **`query(cypher)`** - only when steps 1-2 do not answer the question. Use for relationship pivots: what else a flagged IP hosts, what other domains share a registrant email, who else announces a prefix.

Before any non-trivial Cypher, call `list_labels` or `describe_label("HOSTNAME")` to confirm the label and property exist. They are cached server-side and cheap.

## Important: anti-patterns that time out

The server-side validator rejects these, but do not write them in the first place:

- **Label disjunction** - `MATCH (n) WHERE n:HOSTNAME OR n:DOMAIN OR n:FQDN`. There is no `DOMAIN` or `FQDN` label; only `HOSTNAME`. Pick one label.
- **Unanchored scans** - `MATCH (h:HOSTNAME) RETURN h LIMIT 100` scans a 2.6-billion-node label. Anchor with `{name: "..."}` or traverse from an already-anchored node.
- **Text ops off `.name`** - `CONTAINS` / `STARTS WITH` / `ENDS WITH` are only indexed on the `.name` property.
- **Unbounded paths** - `shortestPath((a)-[*]-(b))` must be bounded: `shortestPath((a)-[*1..6]-(b))`.
- **Missing or oversized `LIMIT`** - every exploration query needs a `LIMIT` and it must be ≤ 500.

## Instructions

### Step 1: Classify the indicator

Determine whether the user gave an IP (v4/v6), a hostname/domain, an ASN (`AS####`), or a CIDR. The tools accept all four. If the user gave a vague target ("our company"), ask for the apex domain before proceeding.

### Step 2: Get the verdict

Call `explain_indicator(indicator)`. Lead your answer with the level and score. If the user only asked "is this malicious?", quote one or two specific feeds from the `sources[]` array and stop - do not run extra queries.

### Step 3: Pivot only if the question needs it

If the user wants context beyond the verdict, pick the smallest pivot that answers it:

- **What else lives here?** Reverse-DNS the IP, or list co-hosted hostnames.
- **Who is behind this?** WHOIS profile, then pivot on a shared registrant email.
- **Has it changed?** `whisper_history(indicator)`.
- **What is the blast radius?** Trace the IP to its prefix and ASN.

Use the patterns in the Examples section. Run `explain_indicator` on any *new* indicator a pivot surfaces - do not hand-walk threat feeds.

### Step 4: Stop and report

Stop as soon as the user's question is answered. A `CRITICAL` verdict with citations is conclusive - do not enumerate 10,000 subdomains afterward. Cite the feeds and sources the tools returned rather than paraphrasing them. Recommend a concrete action: block, allow, or investigate further.

## Examples

### Example 1: "Is 185.220.101.1 malicious?"

Actions:
1. `explain_indicator("185.220.101.1")` → returns level `HIGH`, listed on Tor exit-node feeds.

Result: Report the level, name the feeds, recommend handling per the user's Tor policy. No `query` call needed.

### Example 2: "Who is behind paypa1.com?"

Actions:
1. `explain_indicator("paypa1.com")` → threat verdict for the lookalike.
2. `query` - WHOIS profile:
   ```cypher
   MATCH (h:HOSTNAME {name: "paypa1.com"})
   OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
   OPTIONAL MATCH (h)-[:HAS_EMAIL]->(e:EMAIL)
   OPTIONAL MATCH (h)-[:REGISTERED_BY]->(o:ORGANIZATION)
   RETURN r.name AS registrar, e.name AS contactEmail, o.name AS organization
   ```
3. `query` - pivot on the shared contact email to find the rest of the portfolio:
   ```cypher
   MATCH (h:HOSTNAME {name: "paypa1.com"})-[:HAS_EMAIL]->(e:EMAIL)<-[:HAS_EMAIL]-(other:HOSTNAME)
   WHERE other.name <> "paypa1.com"
   RETURN e.name AS sharedEmail, other.name AS relatedDomain LIMIT 25
   ```

Result: Verdict plus the registrant and any clustered domains. Run `explain_indicator` on the most interesting related domains.

### Example 3: "Map the attack surface of acme.com"

Actions:
1. `query` - enumerate subdomains via the indexed suffix scan:
   ```cypher
   MATCH (h:HOSTNAME) WHERE h.name ENDS WITH ".acme.com"
   RETURN h.name LIMIT 100
   ```
2. `query` - resolve the apex to IPs and trace to the network owner:
   ```cypher
   MATCH (h:HOSTNAME {name: "acme.com"})-[:RESOLVES_TO]->(ip:IPV4)
         -[:BELONGS_TO]->(p:PREFIX)<-[:ROUTES]-(a:ASN)-[:HAS_NAME]->(n:ASN_NAME)
   RETURN ip.name, p.name AS prefix, a.name AS asn, n.name AS network
   ```
3. `explain_indicator` on each IP or ASN that looks suspicious.

Result: A subdomain inventory, the hosting providers, and a threat verdict on anything notable.

## Troubleshooting

### A query was rejected by the validator

The message names the rule. Most common fixes: anchor the `MATCH` with `{name: "..."}`, pick a single label instead of a disjunction, add a `LIMIT` (≤ 500), or bound a `shortestPath` with `[*1..6]`. See the `whisper-cypher` skill for the full rule set.

### `whisper_history` returns `available: false`

The history service timed out. Surface the `retryAfter` value to the user and continue with the rest of the investigation. Do not loop or retry automatically.

### A query returns 0 rows unexpectedly

Almost always an edge direction. WhisperGraph edges are strict and directional - `RESOLVES_TO` is forward DNS only, `MAIL_FOR` and `NAMESERVER_FOR` point from the server toward the domain, `CHILD_OF` goes child → parent. Re-check the direction or load the `whisper-cypher` skill's `references/schema.md`.

### The user gave an indicator type the graph does not anchor well

EMAIL, PHONE, and ORGANIZATION nodes are huge labels - never scan them. Anchor on a specific node value (e.g. `MATCH (e:EMAIL {name: "email:abuse@example.com"})`) and traverse outward.
