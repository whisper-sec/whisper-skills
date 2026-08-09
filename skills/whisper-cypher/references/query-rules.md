# Safety rules, errors, and self-correction

The server checks every query before it runs. Most checks now help rather than reject, and the three
kinds of help behave differently — that distinction is the part people get wrong.

No rule count appears in this file. The live manifest publishes the count the server is actually
enforcing; read it there rather than trusting a number written down here.

## Contents

- [What runs, in order](#what-runs-in-order)
- [The rules](#the-rules)
- [The three self-correction behaviours](#the-three-self-correction-behaviours)
- [Typed error codes](#typed-error-codes)
- [Pre-submit checklist](#pre-submit-checklist)
- [It passed and it is still slow](#it-passed-and-it-is-still-slow)

## What runs, in order

1. **Read-only pre-check.** Any write or administrative clause is rejected before anything else, and it
   is rejected even under an `EXPLAIN` prefix. There is no path through `query` that mutates anything.
2. **Type and value normalisation.** A label or relationship name that is not in the live schema may be
   resolved through an alias map, and a network number normalised to its canonical form. A confident
   correction runs, flagged as rewritten.
3. **The safety rules**, in order. The first failure wins. String literals, comments and backtick-quoted
   identifiers are stripped first, so a value or a comment can never trip a rule.
4. **A plan cost gate.** A query can pass every rule and still be a blow-up — a Cartesian product from
   accidentally disconnected patterns, or an unbounded expansion rooted at a huge label, only shows up
   in the plan. The gate fetches the plan without executing, and rejects only the genuinely explosive
   shapes. It fails open, so it can add a rejection but never silently drop a query that would run.
5. **Idiom correct-and-retry**, after execution fails on an engine error rather than a rule: one bounded
   retry translates a recognised foreign idiom and re-runs. An idiom with no equivalent gets guidance,
   never a fabricated rewrite.

## The rules

| Rule | What it stops | How to satisfy it |
|---|---|---|
| Bounded shortest paths | an unbounded variable-length path inside a shortest-path call | give it a range, for example `[*1..6]`; the returned fix proposes one |
| Row cap | a `LIMIT` above the server's ceiling | nothing to do — an over-cap limit is **clamped and the query runs**, flagged as rewritten |
| No unlabelled match | a pattern with neither a label nor a name anchor | label the node, or anchor it |
| One label per variable | a label disjunction on a single variable, which forces a scan of both | use the label-pipe form `(n:A\|B)`, or introspect and pick one |
| Anchored query-time edges | a fixed-length hop across a computed edge with both endpoints bare | label or anchor one endpoint. A variable-length pattern *is* allowed to follow computed edges — but see the silent-empty warning in the schema notes |
| Indexed text operators | `CONTAINS` / `STARTS WITH` / `ENDS WITH` on anything but `.name` | move the predicate to `.name`, or use equality; the returned fix proposes equality |
| No unanchored scans of large labels | a bare match on a huge label | anchor on an indexed value. Feed sources and categories may **never** be scanned at any size — reach them through an anchored traversal |
| No ordering on internal ids | a greater-than or less-than comparison on `id()` | order on an ordinary indexed property. This one matters most: the id is a **string**, so the comparison evaluates to null and the query **succeeds while matching nothing** |
| Exploration queries carry a limit | a missing `LIMIT` | nothing to do — one is **injected and the query runs**, flagged as auto-limited. Aggregations are exempt |

## The three self-correction behaviours

**Bounding rewrites run automatically.** They only narrow the result to a bounded prefix — same rows,
capped — so the server applies them and runs the query. You get `autoLimited: true` or
`rewritten: true`, and `rewrite` holds the original and effective Cypher. **Tell the user**: they asked
a question and received an answer about a prefix of it.

**Semantic fixes are returned, never run.** When a correction would change *which* rows match, the
response carries a `fix` object — `kind`, `confidence`, `safeToAutoRetry`, and sometimes
`rewrittenCypher`. Some kinds carry no rewritten query because they need a value only you have; supply
it rather than inventing one. Read `safeToAutoRetry` before acting.

**Type normalisation is a warning, not a service.** A query that only succeeded because the server
corrected a stale label is a query that is wrong. Fix the source.

## Typed error codes

Branch on `errorCode`. `retryable` is read straight off the code, so you never have to parse a message
to decide.

| Code | Retry? | Do this |
|---|---|---|
| `SCHEMA_ERROR` | no | a label, property, relationship type or column is wrong — call `explain_schema`, then fix |
| `SYNTAX_ERROR` | no | malformed Cypher — fix it |
| `LIMIT_ERROR` | no | apply the returned fix |
| `VALIDATION_REJECTED` | no | read `suggestion`; apply `fix` if one is attached |
| `QUERY_TOO_EXPENSIVE` | no | stopped for size, not time. Paging will not help — anchor a node, connect the disconnected patterns, or stage the traversal |
| `QUERY_UNSERVABLE` | no | the engine would not plan the shape — reshape it |
| `DEPTH_EXCEEDED` | no | the Cypher is valid but deeper than your plan allows. Shorten it, or read the quota resource for the cap that applies |
| `DB_TIMEOUT` | yes | narrow it first, then retry once |
| `RATE_LIMITED` | yes | back off; do not loop |
| `ENGINE_ERROR` | yes | retry once; the response carries a request id worth passing on |
| `DB_UNAVAILABLE` | yes | report a failed check, never a clean result |

Retry at most once, and only after changing something. Two failures of the same call is a report to the
user, not a third attempt.

There is no `CYPHER_SYNTAX_ERROR`. A syntax problem arrives as `SCHEMA_ERROR` or `SYNTAX_ERROR`.

## Pre-submit checklist

- Anchored on an indexed value, or traversing from a node already bound.
- Wide intermediate hops cut with `WITH ... LIMIT` before they fan out again.
- Every query-time edge written as its own single hop.
- Edge directions checked against the schema notes.
- `LIMIT` present and within the cap, or the query is a pure aggregation.
- Values passed as parameters, not interpolated.
- No ordering on an internal id.
- Optional matches used for sparse registration and geolocation fields.

## It passed and it is still slow

The anchor is too weak. A traversal hanging off a weakly filtered node still touches an enormous number
of rows before any `LIMIT` applies.

In order of effect: anchor on an exact value; add a tighter predicate; cut the widest intermediate hop
with `WITH ... LIMIT`; reduce the hop count; or replace the whole traversal with the procedure that
already does it server-side. Scoring a network by walking down to its addresses and out to their feed
listings is the classic query that times out — the scoring procedure exists precisely for it.

Use `EXPLAIN` to inspect a plan without executing. Note that `EXPLAIN` is more permissive than
execution: it will plan a query that references an edge type or property that does not exist. It tells
you about syntax and shape, not about whether your schema is real — `explain_schema` is what tells you
that.
