# Safety rules, errors, and self-correction

The server checks every query before it runs. Most checks help rather than reject, and the three kinds
of help behave differently. That distinction is the part people get wrong.

No rule count appears in this file. The live manifest publishes the number the server enforces, as
`validationRuleCount`; read it there rather than trusting a number written down here.

## Contents

- [What runs, in order](#what-runs-in-order)
- [The rules](#the-rules)
- [The three self-correction behaviours](#the-three-self-correction-behaviours)
- [Truncation and paging](#truncation-and-paging)
- [Typed error codes](#typed-error-codes)
- [Pre-submit checklist](#pre-submit-checklist)
- [It passed and it is still slow](#it-passed-and-it-is-still-slow)

## What runs, in order

1. **Read-only and single-statement pre-checks.** Any write or administrative clause is rejected before
   anything else, even under an `EXPLAIN` prefix. There is no path through `query` that mutates
   anything. A `;`-separated batch is refused here too.
2. **Type and value normalisation.** A label or relationship name that is not in the live schema may be
   replaced with the nearest one it knows, and a network number normalised to its canonical form. A
   confident replacement runs, flagged as rewritten.
3. **The safety rules**, in order. The first failure wins. String literals, comments and backtick-quoted
   identifiers are stripped first, so a value or a comment can never trip a rule.
4. **A plan cost gate.** A query can pass every rule and still blow up. A Cartesian product from
   accidentally disconnected patterns, or an unbounded expansion rooted at a huge label, only shows in
   the plan. The gate reads the plan without executing and rejects only the genuinely explosive shapes.
   It fails open, so it can add a rejection but never drops a query that would have run. A query that
   is only a procedure call skips it.
5. **Idiom correct-and-retry**, after execution fails on an engine error rather than a rule: one bounded
   retry translates a recognised foreign idiom and re-runs. An idiom with no equivalent gets guidance,
   never a fabricated rewrite.

## The rules

| Rule | What it stops | How to satisfy it |
|---|---|---|
| One statement per call | a `;`-separated batch | split at each top-level `;` and send one statement per call |
| Bounded shortest paths | an unbounded variable-length path inside a shortest-path call | give it a range, for example `[*1..6]`; the returned fix proposes one |
| Row cap | a `LIMIT` above the server's ceiling | nothing to do: an over-cap limit is **clamped and the query runs**, with `rewrite.kind` `CLAMP_LIMIT` |
| No unlabelled match | a pattern with neither a label nor a name anchor | label the node, or anchor it |
| One label per variable | a label disjunction on a single variable, which forces a scan of both | use the label-pipe form `(n:A\|B)`, or introspect and pick one |
| Anchored query-time edges | a fixed-length hop across a computed edge with both endpoints bare | label or anchor one endpoint. A variable-length pattern may follow computed edges |
| Indexed text operators | `CONTAINS`, `STARTS WITH` or `ENDS WITH` on anything but `.name` | move the predicate to `.name`, or use equality; the returned fix proposes equality |
| No unanchored scans of large labels | a bare match on a huge label | anchor on an indexed value. Feed sources and categories may **never** be scanned at any size: reach them through an anchored traversal |
| Identity only on internal ids | an ordering comparison on `id()` | refused, with fix kind `ID_EQUALITY_ONLY`. Use `id()` for equality only; page with `pageSize` and `cursor`, and pick nodes by anchoring on `.name` |
| Exploration queries carry a limit | a limit-less exploration query, such as a prefix scan | nothing to do: a default `LIMIT` is **added and the query runs**, with `rewrite.kind` `AUTO_LIMIT`. Aggregations are exempt. An anchored lookup without a `LIMIT` runs as written, and the response budget may cut it: read `truncated`, `budgetTruncated` and `resultTruncated` |

## The three self-correction behaviours

**Bounding rewrites run automatically.** `AUTO_LIMIT` and `CLAMP_LIMIT` only narrow the result to a
bounded prefix: same rows, capped. The server applies them and runs the query. You get `rewritten: true`
and a `rewrite` object with its `kind` and `confidence`, and `evidence.cypher` holds the query that
actually ran. **Tell the user**: they asked a question and received an answer about a prefix of it.

**Semantic fixes are returned, never run.** When a correction would change *which* rows match, the
response carries a `fix` object with `kind`, `confidence`, `safeToAutoRetry`, and sometimes
`rewrittenCypher`. Some kinds, such as `SPLIT_STATEMENTS` and `ID_EQUALITY_ONLY`, carry no rewritten
query because the change needs a decision or a value only you have; make it rather than inventing one. Read `safeToAutoRetry` before acting. On a failure, `engineSuggestions` may list the
engine's own remedies as well.

**Type normalisation is a warning, not a service.** `rewrite.kind` `TYPE_NORMALIZED` means the server
replaced a label or edge name it did not recognise. Compare `evidence.cypher` with what you sent: the
replacement may be a different edge from the one you meant, and the rows then answer a different
question. Say so to the user, and fix the source.

## Truncation and paging

- **`truncated`**: the row cap cut the result.
- **`budgetTruncated`**: rows were cut further to fit the response size budget.
- **`resultTruncated`**: the result was replaced or cut, with a `reason` and `guidance` to follow.

Any of the three means the rows are a sample, not a census. `pagination` carries `hasMore` and a
`nextCursor`: send the same Cypher and params with `cursor` set for the next page, or set `pageSize` up
front to page from the start.

Paging is by offset, so a row can repeat or go missing between pages. `ORDER BY` a returned property,
such as `n.name`, to page by key. A row that slipped between pages is not an absent one.

## Typed error codes

Branch on `errorCode`. `retryable` is read straight off the code, so you never have to parse a message
to decide.

| Code | Retry? | Do this |
|---|---|---|
| `SCHEMA_ERROR` | no | a label, property, relationship type or column is wrong: call `explain_schema`, then fix |
| `SYNTAX_ERROR` | no | malformed Cypher: fix it |
| `LIMIT_ERROR` | no | a `LIMIT` or `SKIP` the server could not bound, such as one bound to a missing or null parameter: bind it or write a literal, as the returned fix says |
| `VALIDATION_REJECTED` | no | a safety rule failed: read `suggestion`, and apply `fix` if one is attached |
| `MULTI_STATEMENT_REJECTED` | no | split at each top-level `;` and send one statement per call |
| `QUERY_TOO_EXPENSIVE` | no | stopped for size, not time. Paging will not help: anchor a node, connect the disconnected patterns, or stage the traversal with `WITH` |
| `QUERY_UNSERVABLE` | no | the engine refused to plan the shape, or the data is not available to this account. Reshape it; if it persists, say the data is not available rather than reporting an empty result |
| `DEPTH_EXCEEDED` | no | the Cypher is valid but deeper than this account may go: shorten it |
| `DB_TIMEOUT` | yes | narrow it first, then retry once |
| `RATE_LIMITED` | yes | back off; do not loop |
| `ENGINE_ERROR` | yes | retry once; if it persists, report the error to the user |
| `DB_UNAVAILABLE` | yes | report a failed check, never a clean result |

Retry at most once, and only for a retryable code: narrow a timed-out query first, and back off after a
rate limit. Never resend a query that failed for any other reason unchanged. Two failures of the same
call is a report to the user, not a third attempt.

There is no `CYPHER_SYNTAX_ERROR`. A syntax problem arrives as `SCHEMA_ERROR` or `SYNTAX_ERROR`.

## Pre-submit checklist

- One statement.
- Anchored on an indexed value, or traversing from a node already bound.
- Wide intermediate hops cut with `WITH ... LIMIT` before they fan out again.
- At least one endpoint of every query-time hop labelled or anchored.
- Edge directions checked against the schema notes.
- `LIMIT` present and within the cap, or the query is a pure aggregation.
- Values passed as parameters, not interpolated.
- `id()` used for equality only.
- Optional matches used for sparse registration and geolocation fields.
- When paging, an `ORDER BY` on a returned property.

## It passed and it is still slow

The anchor is too weak. A traversal hanging off a weakly filtered node still touches an enormous number
of rows before any `LIMIT` applies.

In order of effect: anchor on an exact value; add a tighter predicate; cut the widest intermediate hop
with `WITH ... LIMIT`; reduce the hop count; or replace the whole traversal with the procedure that
already does it server-side. Scoring a network by walking down to its addresses and out to their feed
listings is the classic query that times out, and the scoring procedure exists precisely for it.

Use `EXPLAIN` to inspect a plan without executing. `EXPLAIN` is more permissive than execution: it will
plan a query that names an edge type or property that does not exist. It tells you about syntax and
shape, not about whether your schema is real; `explain_schema` is what tells you that.
