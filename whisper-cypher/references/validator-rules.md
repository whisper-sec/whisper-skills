# WhisperGraph Validator Rules

Before a Cypher query reaches the database, the WhisperGraph MCP server runs it through a validator. The validator is the primary defense against expensive queries that would degrade availability (the graph has billion-node labels). It enforces seven rules. If a query is rejected, the error message names the rule - fix it and resubmit.

These rules are *not* arbitrary. They exist because static schema docs alone were not enough to stop LLMs from writing defensive scan-everything patterns. Treat a rejection as a signal that the query would have been slow, not as an obstacle.

---

## Rule 1 - Bounded shortestPath

`shortestPath` and `allShortestPaths` must use a bounded variable-length pattern.

- ❌ `MATCH p = shortestPath((a)-[*]-(b))`
- ✅ `MATCH p = shortestPath((a)-[*1..6]-(b))`

Pick the smallest upper bound that can plausibly contain the path. Anchor both endpoints with `{name: ...}`.

## Rule 2 - LIMIT cap (≤ 500)

No query may request more than 500 rows.

- ❌ `... RETURN h.name LIMIT 5000`
- ✅ `... RETURN h.name LIMIT 500`

If you need more than 500 results, you almost certainly want an aggregation (`count`, `collect`) or a tighter filter instead.

## Rule 3 - No standalone unlabeled MATCH

A bare `MATCH (n)` with no label is rejected.

- ❌ `MATCH (n) WHERE n.name = "google.com" RETURN n`
- ✅ `MATCH (n:HOSTNAME) WHERE n.name = "google.com" RETURN n`
- ✅ allowed when the node is part of a relationship traversal, or anchored with `{name: ...}` inline

Always give the node a label. It lets the planner use the right index.

## Rule 4 - No same-variable label disjunction

`WHERE n:A OR n:B` on a single variable is rejected - it forces the planner to scan multiple labels.

- ❌ `MATCH (n) WHERE n:HOSTNAME OR n:DOMAIN OR n:FQDN RETURN n`
- ✅ pick one label - `MATCH (n:HOSTNAME) ...` (and remember `DOMAIN`/`FQDN` do not exist)
- ✅ the label-pipe form is allowed - `MATCH (n:HOSTNAME|IPV4) ...`
- ✅ property disjunction is allowed - `WHERE n.threatLevel = "HIGH" OR n.threatLevel = "CRITICAL"`

This rule directly targets the defensive "match anything that might be a domain" anti-pattern.

## Rule 5 - Unindexed text ops only on `.name`

`CONTAINS`, `STARTS WITH`, and `ENDS WITH` are only allowed on the `.name` property, which is text-indexed on every label.

- ❌ `WHERE h.threatSources CONTAINS "spamhaus"`
- ❌ `WHERE r.description STARTS WITH "Market"`
- ✅ `WHERE h.name ENDS WITH ".google.com"`
- ✅ `WHERE n.name STARTS WITH "GOOGLE"`
- ✅ equality (`=`) is allowed on any property

If you need a substring match on a non-`.name` property, you cannot - restructure the query to anchor differently.

## Rule 6 - No unanchored scan of a large label

A `MATCH` on a large label with no anchor (no `{name: ...}`, no indexed text predicate on `.name`, no incoming traversal) is rejected.

- ❌ `MATCH (h:HOSTNAME) RETURN h LIMIT 100`
- ❌ `MATCH (a:ASN) RETURN a LIMIT 100`
- ✅ `MATCH (h:HOSTNAME {name: "google.com"}) ...` - anchored
- ✅ `MATCH (h:HOSTNAME) WHERE h.name ENDS WITH ".google.com" ...` - indexed text predicate
- ✅ `MATCH (ip:IPV4 {name: "8.8.8.8"})<-[:RESOLVES_TO]-(h:HOSTNAME) ...` - reached by traversal
- ✅ `MATCH (c:COUNTRY) RETURN c.name LIMIT 50` - small label, safe to scan

Small labels exempt from this rule: `COUNTRY`, `RIR`, `TLD`, `TLD_OPERATOR`, `DNSSEC_ALGORITHM`, `CATEGORY`. Note `FEED_SOURCE` is **not** exempt - it is virtual and scanning it times out; reach feeds via `LISTED_IN` from an anchored indicator.

## Rule 7 - LIMIT required on exploration queries

Any query that returns raw rows must include a `LIMIT`.

- ❌ `MATCH (ip:IPV4 {name: "8.8.8.8"})<-[:RESOLVES_TO]-(h:HOSTNAME) RETURN h.name`
- ✅ `... RETURN h.name LIMIT 100`

**Exempt**: aggregation queries (the result is bounded by construction) and `EXPLAIN` / `PROFILE`.

- ✅ `MATCH (ip:IPV4 {name: "8.8.8.8"})<-[:RESOLVES_TO]-(h:HOSTNAME) RETURN count(h)` - aggregation, no LIMIT needed
- ✅ `EXPLAIN MATCH (h:HOSTNAME {name: "google.com"}) RETURN h` - EXPLAIN, no LIMIT needed

---

## Pre-submit checklist

1. Every `MATCH` is anchored - `{name: ...}`, an indexed `.name` text predicate, a traversal, or a small label.
2. One label per node variable - no `WHERE n:A OR n:B`.
3. `CONTAINS` / `STARTS WITH` / `ENDS WITH` only on `.name`.
4. `LIMIT` present on every row-returning query, and ≤ 500.
5. Every `shortestPath` is bounded with `[*1..N]`.
6. Aggregations and `EXPLAIN`/`PROFILE` are the only things that may skip `LIMIT`.

## When a query is still slow despite passing

The validator catches *shape* problems, not all *cost* problems. A query can pass and still be slow if the anchor is weak (a traversal hanging off a node matched by a broad `WHERE`). Tighten the anchor, reduce hop count, or convert to an aggregation. Use `PROFILE <query>` to see per-operator timing.
