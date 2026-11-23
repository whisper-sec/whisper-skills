# When the connector will not answer

Every failure mode, what the user sees, and the fix. Work down the list: the first match is almost
always the real cause.

## Contents

- [Checking the connection](#checking-the-connection)
- [The failure table](#the-failure-table)
- [Typed errors from the query tool](#typed-errors-from-the-query-tool)
- [Self-correction: three behaviours, not one](#self-correction-three-behaviours-not-one)
- [Latency: what to warn about first](#latency-what-to-warn-about-first)
- [Checking the service without the connector](#checking-the-service-without-the-connector)

## Checking the connection

When the user asks whether WhisperGraph is connected, call `explain_schema` with no arguments. It touches
no user data, is cached server-side, and returns in milliseconds. Whatever it does tells you which row
below you are in. After a failed call, read the failure itself against the table below rather than
making another call to probe.

## The failure table

| Symptom | Cause | Fix |
|---|---|---|
| The tools do not appear at all | The connector was never added, or the client is holding a stale session | Add WhisperGraph from the client's connector or plugin directory where it is listed; otherwise add `https://mcp.whisper.security` as a custom connector. Then sign in. If it was added, disconnect and reconnect: a stale session is the usual cause of a wrong tool list |
| `401`, `unauthorized`, `invalid token` | The connector is added but the sign-in never completed | Open the connector in the client's settings, connect it again, and let the browser reach the page that says the window can be closed |
| A tool these skills name is missing | A client holding an older session | Disconnect and reconnect. The tool list can differ between clients, but every tool these skills call is listed in every client |
| A tool call never returns | The run went past the client's tool-call timeout | Use a lighter call. For `map_infrastructure` and `map_supply_chain`, drop to the default `level` |
| The client shows tool names with a prefix, such as `mcp__…__` | Normal. Some clients namespace connector tools | Ignore the prefix; the tool is the last segment |

The setup guide covers each client's steps: https://www.whisper.security/docs/ai/mcp/setup

Do not, in any of these states, answer the user's indicator question from your own knowledge. Say the
connector is unavailable and that the indicator is unresolved.

## Typed errors from the query tool

`query` returns a typed envelope rather than free text, so branch on `errorCode` rather than parsing a
message. `retryable` is read straight off the code, and `suggestion` says what to change.

| Code | What to do |
|---|---|
| `SCHEMA_ERROR` | A label, property, relationship type or column name is wrong. Call `explain_schema` for the entity, then fix the query. Never retry unchanged |
| `SYNTAX_ERROR` | Malformed Cypher. Fix it. Never retry unchanged |
| `LIMIT_ERROR` | A `LIMIT` or `SKIP` the server could not bound, such as one bound to a parameter that is missing or null. Bind the parameter or write a literal, as the returned fix says |
| `VALIDATION_REJECTED` | A query-safety rule failed. Read `suggestion`, and apply `fix` if one is attached; see below |
| `MULTI_STATEMENT_REJECTED` | More than one statement in one call. Split at each top-level `;` and send one statement per call |
| `QUERY_TOO_EXPENSIVE` | Stopped for size, not duration. Paging will not help. Anchor a node, connect the disconnected patterns, or stage the traversal with `WITH` |
| `QUERY_UNSERVABLE` | The engine refused to plan the shape, or the data is not available to this account. Reshape it: anchor the scan, or split the query-time hop out. If it persists, say the data is not available rather than reporting an empty result |
| `DEPTH_EXCEEDED` | The traversal is deeper than this account may go. The Cypher is valid. Shorten it |
| `DB_TIMEOUT` | Retryable, but not unchanged: narrow it first, then retry once |
| `RATE_LIMITED` | Retryable. Back off; do not loop |
| `ENGINE_ERROR` | Retryable once. If it persists, report the error to the user |
| `DB_UNAVAILABLE` | Retryable. Report it as a failed check, never as a clean result |

Retry at most once, and only for a retryable code: narrow a timed-out query first, and back off after a
rate limit. Never resend a query that failed for any other reason unchanged. Two failures of the same
call is a report to the user, not a third attempt.

There is no `CYPHER_SYNTAX_ERROR` code. If you are branching on that name, you are working from an old
contract.

## Self-correction: three behaviours, not one

The server does more than reject, and the three behaviours need different handling.

**Bounding rewrites run automatically.** A missing `LIMIT` on an exploration query is added, and an
over-cap one is lowered, and the query runs. The response carries `rewrite` with its `kind`, `AUTO_LIMIT`
or `CLAMP_LIMIT`, and `evidence.cypher` holds the query that actually ran. **Tell the user the result was bounded**: they asked a question and got an
answer about a prefix of it.

**Semantic fixes are returned, never run.** When a correction would change *which* rows match, the
response carries a `fix` object with `kind`, `confidence` and `safeToAutoRetry`. Read `safeToAutoRetry`.
Some fixes need a value only you have: supply it, do not invent one.

**Type normalisation runs before the rules.** A label or relationship name outside the server's schema
may be resolved to the nearest known name and the corrected query run, flagged with a `rewrite` of kind
`TYPE_NORMALIZED`. Compare `evidence.cypher` with what you sent: the query that ran may not be the one
you meant. Fix the source rather than relying on the correction.

## Latency: what to warn about first

| Class | Calls | Behaviour |
|---|---|---|
| Instant, cached | `explain_schema`, `read_docs` | Call when needed, no warning |
| Fast | `explain_indicator`, `identify`, an anchored `query` | Call freely |
| Seconds | the named investigation tools at their default level | Fine; say what you are running |
| Can run long | `map_infrastructure` or `map_supply_chain` above the default `level`, on a large estate | **Warn before calling**, and offer the default level first |

A verdict over many hostnames belongs in one `explain_indicator` call with `detail: "band"`, rather than
in many individual scored calls.

## Checking the service without the connector

If you can run a shell command and need to know whether the problem is the client or the service, the
public graph API answers anonymously, with no key and no account:

```bash
curl -sS -A "whisper-connectivity-check/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.quota() YIELD key, value RETURN key, value"}' \
  https://graph.whisper.security/api/query
```

A JSON body back means the service is up and the problem is the connector. An HTTP error means the
service. Send an explicit `User-Agent`: a default programmatic agent string can be rejected at the edge
with a 403 that looks like an outage.

This is a connectivity test only, not an investigation path. The `whisper-cypher` skill's HTTP API
reference covers what the anonymous API can and cannot do; each skill is self-contained, so load that
skill rather than following a path across directories.
