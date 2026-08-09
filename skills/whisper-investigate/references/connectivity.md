# When the connector will not answer

Every failure mode, what the user sees, and the fix. Work down the list — the first match is almost
always the real cause.

## Contents

- [Triage in one call](#triage-in-one-call)
- [The failure table](#the-failure-table)
- [Typed errors from the query tool](#typed-errors-from-the-query-tool)
- [Self-correction: three behaviours, not one](#self-correction-three-behaviours-not-one)
- [Latency: what to warn about first](#latency-what-to-warn-about-first)
- [Checking the service without the connector](#checking-the-service-without-the-connector)

## Triage in one call

`explain_schema` with no arguments is the probe. It needs no arguments, touches no user data, is cached
server-side, and returns in milliseconds. Whatever it does tells you which row below you are in.

## The failure table

| Symptom | Cause | Fix |
|---|---|---|
| The tool does not appear at all | The connector was never added, or the client is holding a stale session | Add `https://mcp.whisper.security` as a custom connector, or run `/whisper-setup` in Claude Code. If it was added, disconnect and reconnect — a stale session is the usual cause of a wrong tool list |
| `401`, `unauthorized`, `invalid token` | The connector is added but the sign-in never completed | Settings → Connectors → *whisper-graph* → Connect, and let the browser reach the "you can close this window" page |
| `insufficient_scope` on a submit call | The token was granted read scope only | Expected and correct. The read surface is unaffected. Do not retry |
| The tool list has the wrong number of entries | Almost always a client holding an older session | Disconnect and reconnect. The advertised surface does not vary by plan, tier, or setting |
| Everything works, but a workflow never returns | The call ran past the client's tool-call timeout | Use a lighter workflow. `indicator-enrichment` answers most of what the deepest dive answers, in seconds |
| The client shows tool names prefixed `mcp__…__` | Normal. Some clients namespace MCP tools | Ignore the prefix; the tool is the last segment |

Do not, in any of these states, answer the user's indicator question from your own knowledge. Say the
connector is unavailable and that the indicator is unresolved.

## Typed errors from the query tool

`query` returns a typed envelope rather than free text, so branch on `errorCode` rather than parsing a
message. `retryable` is read straight off the code.

| Code | What to do |
|---|---|
| `SCHEMA_ERROR` | A label, property, relationship type or column name is wrong. Call `explain_schema` for the entity, then fix the query. Never retry unchanged |
| `SYNTAX_ERROR` | Malformed Cypher. Fix it. Never retry unchanged |
| `LIMIT_ERROR` | The `LIMIT` is missing, malformed, or over the cap. Apply the returned fix |
| `VALIDATION_REJECTED` | A query-safety rule failed. Read `suggestion`, and apply `fix` if one is attached — see below |
| `QUERY_TOO_EXPENSIVE` | Stopped for size, not duration. Paging will not help. Anchor a node, connect the disconnected patterns, or stage the traversal with `WITH` |
| `QUERY_UNSERVABLE` | The engine refused to plan the shape. Reshape it — anchor the scan, or split the virtual-edge hop out |
| `DEPTH_EXCEEDED` | The traversal is deeper than the plan allows. The Cypher is valid. Shorten it, or read the quota resource to see the cap that applies |
| `DB_TIMEOUT` | Retryable, but not unchanged — narrow it first, then retry once |
| `RATE_LIMITED` | Retryable. Back off; do not loop |
| `ENGINE_ERROR` | Retryable once. The response carries a request id — give it to the user if it persists |
| `DB_UNAVAILABLE` | Retryable. Report it as a failed check, never as a clean result |

Retry at most once, and only for a retryable code. Two failures of the same call is a report to the
user, not a third attempt.

There is no `CYPHER_SYNTAX_ERROR` code. If you are branching on that name, you are working from an old
contract.

## Self-correction: three behaviours, not one

The server does more than reject, and the three behaviours need different handling.

**Bounding rewrites run automatically.** A missing or over-cap `LIMIT` is added or clamped and the query
runs. The response says so with `autoLimited: true` or `rewritten: true` and carries both the original
and effective Cypher. **Tell the user the result was bounded** — they asked a question and got an
answer about a prefix of it.

**Semantic fixes are returned, never run.** When a correction would change *which* rows match, the
response carries a `fix` object with `kind`, `confidence`, `safeToAutoRetry`, and sometimes
`rewrittenCypher`. Read `safeToAutoRetry`. Some fixes carry no rewritten query because they need a value
only you have — supply it, do not invent one.

**Type normalisation runs before the rules.** A label or relationship name outside the live schema may
be resolved through an alias map and the corrected query run, flagged `rewritten: true`. Treat that as a
signal your query was wrong, and fix the source — a shipped pattern that only works because the server
was forgiving is a pattern that will break.

## Latency: what to warn about first

| Class | Calls | Behaviour |
|---|---|---|
| Instant, cached | `explain_schema`, `read_docs`, `list_workflows` | Call freely, no warning |
| Fast | `explain_indicator`, `identify`, an anchored `query` | Call freely |
| Seconds | most gallery workflows | Fine unattended; say what you are running |
| May exceed the client's tool-call timeout | the deepest single-indicator workflow, and attack surface above `level: quick` | **Warn before calling**, and offer the lighter alternative |

A bulk verdict over many hostnames belongs in `detail: "band"`, which is one call, rather than in many
individual scored calls.

## Checking the service without the connector

If you need to know whether the problem is the client or the service, the public graph API answers
anonymously — no key, no account:

```bash
curl -sS -A "whisper-connectivity-check/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.quota() YIELD key, value RETURN key, value"}' \
  https://graph.whisper.security/api/query
```

A JSON body back means the service is up and the problem is the MCP connection. An HTTP error means the
service. Send an explicit `User-Agent`: a default programmatic agent string can be rejected at the edge
with a 403 that looks like an outage.

This is a connectivity test only, not an investigation path. The `whisper-cypher` skill's REST
reference covers what the keyless tier can and cannot do; each skill is self-contained, so load that
skill rather than following a path across directories.
