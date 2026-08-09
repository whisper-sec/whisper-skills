# Reaching the graph over HTTP

The MCP connector is the supported path for an assistant, and everything in the other skills assumes it.
This file exists for the two cases the connector does not cover: a client with no MCP support, and a
script or CI job that needs to check something without a session.

**This is not an investigation path.** The HTTP API does not enforce the connector's query-safety rules,
does not return the coverage block, the evidence trail, the typed error envelope, or any of the
self-correction fields. A query that passes here can still be rejected by the connector, and a verdict
read here arrives without the qualifications that make it safe to report. Use it to check connectivity,
to validate a query's shape, or to script something small — not to answer a security question.

## The endpoint

One endpoint, `POST https://graph.whisper.security/api/query`, with a JSON body.

```bash
curl -sS -A "your-tool-name/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.quota() YIELD key, value RETURN key, value"}' \
  https://graph.whisper.security/api/query
```

The body field is **`query`**, and bound values go in **`parameters`**. A `GET` variant takes the query
as `?q=`, and a statistics endpoint at `/api/query/stats` returns live graph totals in one cheap call —
use it instead of any whole-graph aggregate.

```bash
curl -sS -A "your-tool-name/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.assess([$v]) YIELD host, label, band","parameters":{"v":"8.8.8.8"}}' \
  https://graph.whisper.security/api/query
```

**Always send an explicit `User-Agent`.** The edge rejects some default programmatic agent strings with
a 403 that looks exactly like an outage. Any descriptive string avoids it. This bites scripted clients
hardest, because their language's default agent string is often the one that gets blocked.

## The response

Every success returns the same three fields: `columns`, `rows` — one object per row, keyed by column
name — and `statistics` with the row count and server-side execution time. Errors come back as
`application/problem+json` with a type, title, status, detail, and usually a suggestions array.

Note what is *not* there: no coverage block, no evidence block, no typed `errorCode`, no `autoLimited`,
`rewritten`, `fix`, or `truncations`. Those are connector fields.

## Keyless and keyed

There is a real keyless tier, and it returns real answers.

Without a key you can call the direct read procedures — coverage-qualified assessment, host identity,
threat scoring, lookalike generation, structural neighbourhood, origin discovery, history — and run
shallow Cypher. It is rate-limited per source address and shallow in traversal depth. It is a taste,
not a foundation: build anything real on a key.

With a key, sent as `X-API-Key`, the rate limit lifts and deeper traversal and the rest of the surface
open up. `Authorization: Bearer <key>` and `Authorization: ApiKey <key>` are also accepted.

Ask the graph what tier you are actually on rather than assuming — this call never counts against quota:

```cypher
CALL whisper.quota() YIELD key, value
RETURN key, value
```

It reports the plan, whether the request is anonymous, the traversal-depth cap, the response-row caps,
the timeout, the concurrency limit, and the remaining hourly and daily budget.

**An invalid key does not fail the request.** It silently degrades to the anonymous tier. Shallow-looking
results, a depth error on a query that used to work, or an unexpected rate limit almost always mean a
bad or missing header — check the tier before you debug the query.

## Handling a key

Read it from the environment. Never write it into a file that is committed, never paste it into a chat,
never embed it in a skill or a plugin, and never log it.

```bash
curl -sS -A "your-tool-name/1.0" \
  -H "X-API-Key: ${WHISPER_API_KEY:?set WHISPER_API_KEY}" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.quota() YIELD key, value RETURN key, value"}' \
  https://graph.whisper.security/api/query
```

Keys are issued from the Whisper Security console. Revoke a key there if it is ever exposed.

For MCP clients that cannot complete a browser sign-in, the same key works as a bearer header on the
connector, and there is a bridge for clients that speak only local transports. The setup guide in the
documentation covers the per-client configuration.

## Limits worth knowing before you script against it

- Queries are time-capped, and the cap is lower on the anonymous tier than on a key. Exceeding it
  returns an HTTP error, not a partial result.
- Traversal depth is capped by tier. A deep query that returns nothing on the anonymous tier has hit the
  cap, not found nothing.
- Concurrency is capped. On the anonymous tier it is one request at a time; a parallel script will
  serialise or fail.
- The anonymous quota is keyed to your source address. On a connection with rotating addresses the
  counter resets unpredictably — do not treat it as a stable budget.
- Metadata and introspection calls do not count against quota.
