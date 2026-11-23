# Reaching the graph over HTTP

The MCP connector is the supported path for an assistant, and everything in the other skills assumes it.
This file exists for the two cases the connector does not cover: a client with no MCP support, and a
script or CI job that needs to check something without a session.

**This is not an investigation path.** The HTTP API does not run the connector's query-safety rules, and
it returns no coverage block, no evidence trail, no typed error envelope, and none of the connector's
self-correction fields beyond a bare note when the engine rewrites a label. A
query that passes here can still be rejected by the connector, and a verdict read here arrives without
the qualifications that make it safe to report. Use it to check connectivity, to validate a query's
shape, or to script something small. Do not use it to answer a security question.

## The endpoint

One endpoint, `POST https://graph.whisper.security/api/query`, with a JSON body.

```bash
curl -sS -A "your-tool-name/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.quota() YIELD key, value RETURN key, value"}' \
  https://graph.whisper.security/api/query
```

The body field is **`query`**, and bound values go in **`parameters`**. A `GET` variant takes the query
as `?q=`. A statistics endpoint at `/api/query/stats` returns live graph totals in one cheap call: use it
instead of any whole-graph aggregate.

```bash
curl -sS -A "your-tool-name/1.0" \
  -H 'content-type: application/json' \
  --data '{"query":"CALL whisper.assess([$v]) YIELD host, label, band RETURN host, label, band","parameters":{"v":"8.8.8.8"}}' \
  https://graph.whisper.security/api/query
```

Send a descriptive `User-Agent` naming your tool. If a scripted call is refused with a 403 while the same
query works from elsewhere, the agent string is the first thing to change.

## The response

A success returns `columns`, `rows`, one object per row keyed by column name, and `statistics` with the
row count and server-side execution time. Two more fields appear when they apply:

- **`advisories`**: notes from the engine about a run that succeeded, each with a `kind` and a `message`.
  Some say a column was withheld from this caller, which makes an empty value withheld rather than
  absent. Surface them.
- **`rewrittenQuery`**: the engine corrected a drifted label, such as `DOMAIN` to `HOSTNAME`, and ran the
  corrected query. An advisory names the change. Fix the source.

Errors come back as `application/problem+json` with a `type`, `title`, `status`, `detail`, and usually a
`suggestions` array.

What is *not* there: no coverage block, no evidence block, no typed `errorCode`, no `fix`, no
`pagination`. Those are connector fields.

## Keyless and keyed

Keyless access is real, and it returns real answers.

Without a key you can call the direct read procedures, such as coverage-qualified assessment, host
identity, threat scoring, look-alike generation, structural neighbourhood, origin discovery and history,
and run shallow Cypher. It is rate-limited per source address and shallow in traversal depth, and some
columns come back empty, with an advisory saying which.

With a key, sent as `X-API-Key`, the rate limit rises and deeper traversal and the rest of the surface
open up. `Authorization: Bearer <key>` and `Authorization: ApiKey <key>` are also accepted.

Ask the graph what access you actually have rather than assuming. This call never counts against quota:

```cypher
CALL whisper.quota() YIELD key, value
RETURN key, value
```

It reports whether the request is anonymous, the key's status, the traversal-depth cap, the timeouts,
the response-row caps, the concurrency limit, and the remaining hourly and daily budget.

**An invalid key does not fail the request.** It falls back to keyless access. The `X-Key-Status`
response header, and the `keyStatus` row above, say why: `absent` when no key arrived, `malformed` when
one arrived and could not be read. Shallow-looking results, a depth error on a query that used to work,
or an unexpected rate limit almost always mean a bad or missing header. Check the key status before you
debug the query.

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
connector. The setup guide at https://www.whisper.security/docs/ai/mcp/setup covers the per-client
configuration.

## Limits worth knowing before you script against it

- Queries are time-capped, and the cap is lower without a key. Exceeding it returns an HTTP error, not a
  partial result.
- Traversal depth is capped. A query deeper than the cap is refused with a `query-depth-exceeded`
  problem that states the depth it needed and the cap it hit. It is never an empty result.
- Concurrency is capped. Without a key it is one request at a time, so a parallel script will serialise
  or fail.
- The anonymous quota is keyed to your source address. On a connection with rotating addresses the
  counter resets unpredictably, so do not treat it as a stable budget.
- Metadata and introspection calls do not count against quota.
