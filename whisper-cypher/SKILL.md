---
name: whisper-cypher
description: Write efficient, valid Cypher queries against the WhisperGraph MCP server's internet graph (20 node labels, 29 edge types covering DNS, BGP, WHOIS, GeoIP, email, and threat intelligence). Use when the user wants to query, analyze, or explore WhisperGraph, asks how to traverse the graph, hits a query that was rejected or timed out, asks about the schema or edge directions, or needs analytical or aggregate graph questions answered. Bundles the full schema reference, a validated query cookbook organized by analyst persona, and the server's seven validation rules so queries return in milliseconds instead of being rejected.
license: MIT
compatibility: Requires the WhisperGraph MCP server to be configured in the client. Uses its query, list_labels, and describe_label tools.
metadata:
  author: Whisper Security
  version: 1.0.0
  mcp-server: whisper-graph
---

# Writing Cypher for WhisperGraph

WhisperGraph is a 7.4-billion-node graph of internet infrastructure, queried with Cypher through the WhisperGraph MCP server's `query` tool. The graph is huge, so the server runs a validator that rejects expensive queries before they execute. This skill makes queries pass that validator *and* return fast.

The single most important habit: **anchor every query.** Start from a known node value (`{name: "..."}`) or a small label, then traverse outward. Never scan a billion-node label.

## Important: bundled references

Consult these before writing anything non-trivial:

- **`references/schema.md`** - every node label, every edge type, edge directions, threat-intel properties, and the introspection procedures. Read this when you are unsure which label or edge exists, or which way an edge points.
- **`references/cookbook.md`** - ~60 validated query patterns organized by analyst persona (SOC, threat intel, red team, brand protection, DNS/email, BGP, compliance, research). Start here - copy the closest pattern and adapt it.
- **`references/validator-rules.md`** - the seven rules the server enforces, what each rejects, and how to satisfy it. Read this when a query was rejected.

When in doubt about a label or property at runtime, call the `list_labels` and `describe_label` MCP tools - they are cached server-side for 5 minutes and prevent the most common bug (writing `WHERE h.fqdn = "..."` when the indexed property is `h.name`).

## Important: schema facts that are not intuitive

- There is **no** `DOMAIN` or `FQDN` label - only `HOSTNAME`. Apex domains, subdomains, nameservers, and mail servers all share that one label.
- The indexed string property is `.name` on **every** label. ASN numbers, IPs, CIDRs, emails - all stored as `.name`.
- `FEED_SOURCE`, `CATEGORY`, `REGISTERED_PREFIX`, and `ANNOUNCED_PREFIX` are **virtual** labels. Never scan them directly - traverse into them from an anchored node.
- Edge directions are strict. `RESOLVES_TO` is forward DNS only. `MAIL_FOR` / `NAMESERVER_FOR` point from server → domain. `CHILD_OF` goes child → parent. `ANNOUNCED_BY` targets `ANNOUNCED_PREFIX`, not `ASN`. `LOCATED_IN` goes IP → `CITY` only - chain through `HAS_COUNTRY` for the country.

## Instructions

### Step 1: Confirm the schema

If the query touches a label, edge, or property you are not certain about, check `references/schema.md` or call `describe_label`. Guessing property names is the top cause of failed queries.

### Step 2: Anchor the query

Every query must start from one of:
- an indexed node lookup - `MATCH (h:HOSTNAME {name: "google.com"})`
- a small label that is safe to scan - `COUNTRY`, `RIR`, `TLD`, `TLD_OPERATOR`, `DNSSEC_ALGORITHM`, `CATEGORY`
- a traversal from a node already bound earlier in the query

Never start from an unanchored `MATCH` on `HOSTNAME`, `IPV4`, `IPV6`, `PREFIX`, `EMAIL`, `PHONE`, `ORGANIZATION`, `ASN`, or `ASN_NAME`.

### Step 3: Respect edge directions

If a query returns 0 rows unexpectedly, the edge direction is almost certainly wrong. Check the "Edge-direction landmines" section of `references/schema.md`, or run `EXPLAIN <query>` to inspect the plan without executing.

### Step 4: Satisfy the validator

Before submitting, check the query against the seven rules in `references/validator-rules.md`. The quick checklist:
- Bounded `shortestPath` / `allShortestPaths` (`[*1..N]`).
- `LIMIT` present on exploration queries, and `LIMIT` ≤ 500.
- No standalone unlabeled `MATCH (n)`.
- No same-variable label disjunction (`WHERE n:A OR n:B`).
- `CONTAINS` / `STARTS WITH` / `ENDS WITH` only on `.name`.
- No unanchored scan of a large label.

Aggregations (`count`, `collect`, …) and `EXPLAIN` / `PROFILE` are exempt from the `LIMIT` requirement.

### Step 5: Run and refine

Submit through the `query` MCP tool. If it is rejected, the error names the rule - fix it per `references/validator-rules.md` and resubmit. If it executes but returns 0 rows, suspect edge direction. If it times out, the anchor is too weak - tighten it.

## Examples

### Example 1: "Trace 104.16.123.96 to its network owner"

Anchored single-IP lookup, 5-hop traversal - the canonical pattern:
```cypher
MATCH (ip:IPV4 {name: "104.16.123.96"})-[:BELONGS_TO]->(p:PREFIX)
      <-[:ROUTES]-(a:ASN)-[:HAS_NAME]->(n:ASN_NAME)
RETURN ip.name, p.name AS prefix, a.name AS asn, n.name AS network
```

### Example 2: "How many domains are co-hosted on that IP?"

Count first - do not enumerate a potentially huge set:
```cypher
MATCH (ip:IPV4 {name: "104.16.123.96"})<-[:RESOLVES_TO]-(h:HOSTNAME)
RETURN count(h) AS cohostedDomains
```
Aggregations are exempt from the `LIMIT` rule.

### Example 3: "My query for subdomains of google.com keeps getting rejected"

Likely an unanchored `MATCH (h:HOSTNAME)`. The validator allows an **indexed suffix scan** on `.name`:
```cypher
MATCH (h:HOSTNAME) WHERE h.name ENDS WITH ".google.com"
RETURN h.name LIMIT 100
```
This works because `ENDS WITH` on `.name` is indexed. The same predicate on any other property would be rejected.

## Troubleshooting

### "Query rejected: unanchored label scan"

The `MATCH` starts from a large label with no `{name: ...}` filter and no incoming traversal. Anchor it, or - if you genuinely need a text search - use `STARTS WITH` / `ENDS WITH` / `CONTAINS` on `.name`. See `references/validator-rules.md`, rule 6.

### "Query rejected: missing LIMIT"

Add `LIMIT` (≤ 500) to any exploration query. If the query is purely an aggregation, it should already be exempt - check that you are returning `count(...)` / `collect(...)` and not raw rows.

### "Query rejected: label disjunction" or "unbounded shortestPath"

You wrote `WHERE n:A OR n:B` on one variable, or an unbounded variable-length path. Pick one label (or use the `(n:A|B)` label-pipe form), and bound paths with `[*1..6]`. See `references/validator-rules.md`, rules 1 and 4.

### Query executes but returns 0 rows

Edge direction. Re-read "Edge-direction landmines" in `references/schema.md`. Common ones: `(ip)-[:ANNOUNCED_BY]->(:ASN)` is wrong (target is `ANNOUNCED_PREFIX`); `(domain)-[:MAIL_FOR]->(mx)` is reversed (use `<-[:MAIL_FOR]-`); `(:IPV4)-[:RESOLVES_TO]->(:HOSTNAME)` is wrong (forward DNS only - use `<-[:RESOLVES_TO]-`).

### Query is slow or times out

The anchor is too weak. A traversal hanging off a weakly-filtered node still touches millions of rows. Anchor on a specific `{name: ...}` value, add a tighter `WHERE`, or reduce the hop count. Expected timings are in `references/cookbook.md` under "Performance expectations".

### Need an analytical answer, not a list

Use the aggregation and list functions documented at the end of `references/schema.md` (`count`, `count(DISTINCT ...)`, `collect`, `percentile_disc`, `reduce`, …). Aggregations skip the `LIMIT` requirement and are the right tool for "how many", "average", "top N" questions.
