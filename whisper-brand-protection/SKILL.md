---
name: whisper-brand-protection
description: Run typosquatting and brand-protection sweeps with the WhisperGraph MCP server. Use when the user wants to find lookalike or typosquatted domains of a brand, asks which fake domains impersonate their company, or mentions brand protection, domain monitoring, phishing-domain discovery, or takedown preparation. Generates registered lookalikes with the domain_variants tool, screens which are weaponized against threat feeds, pivots to the registrant via WHOIS, and formats a prioritized monitoring and takedown report.
license: MIT
compatibility: Requires the WhisperGraph MCP server to be configured in the client. Uses its domain_variants, query, and explain_indicator tools. The report script needs Python 3.8+ in the execution environment.
metadata:
  author: Whisper Security
  version: 1.0.0
  mcp-server: whisper-graph
---

# WhisperGraph Brand-Protection Sweep

Find domains that impersonate a brand, decide which ones are dangerous, attribute them, and produce a report a SOC or legal team can act on. This skill drives the WhisperGraph MCP server's `domain_variants`, `query`, and `explain_indicator` tools.

The mental model: `domain_variants` tells you what *exists*; the threat feeds tell you what is *weaponized*; WHOIS tells you *who* is behind it. Run all three, in that order.

## Important: "exists" is not "malicious"

`domain_variants` returns variants that are **registered** as graph nodes. A registered lookalike is a *candidate*, not a verdict. Many are defensive registrations by the brand itself or by unrelated parties. Always screen candidates through threat feeds and `explain_indicator` before calling anything malicious.

## Important: workflow

1. **`domain_variants(name)`** - generate registered lookalikes (14 algorithms: omission, homoglyph, bitsquatting, TLD-swap, …). Defaults to existing-graph-nodes only. Each variant carries a `method` and a `confidence` score.
2. **`query`** - batch-screen the candidates against threat feeds in one Cypher call.
3. **`explain_indicator(variant)`** - get a full structured verdict for each variant that screened as suspicious.
4. **`query`** - pivot through WHOIS to attribute the worst offenders to a registrant.
5. **`scripts/format_sweep.py`** - turn the collected results into a prioritized Markdown + CSV report.

## Instructions

### Step 1: Generate registered lookalikes

Call `domain_variants` with the brand's apex domain. Keep the default (existing nodes only) for an actionable sweep; pass the "include unregistered" option only when the user explicitly wants a watchlist of domains an actor *might* register next. Note that homoglyph hits on Unicode confusables come back in punycode (`xn--…`) form.

### Step 2: Screen for weaponization

Batch-check the candidates against threat feeds in a single query. This is the validated pattern:
```cypher
CALL whisper.variants("paypal.com") YIELD variant, method, exists, confidence
WHERE exists = true
WITH variant, method, confidence ORDER BY confidence DESC LIMIT 50
MATCH (h:HOSTNAME {name: variant})
OPTIONAL MATCH (h)-[:LISTED_IN]->(f:FEED_SOURCE)
RETURN h.name, method, confidence, h.threatLevel, h.threatScore,
       collect(f.name) AS feeds
ORDER BY h.threatScore DESC
```
A variant with `feeds` populated or a non-null `threatLevel` is weaponized. A variant with neither is *registered but not yet flagged* - still worth monitoring, especially high-confidence homoglyph and bitsquatting hits.

### Step 3: Get verdicts on the suspicious ones

For each variant that screened as suspicious, call `explain_indicator(variant)`. Use the returned score, level, `factors[]`, and `sources[]` - quote specific feeds rather than paraphrasing.

### Step 4: Attribute the worst offenders

For each high-interest variant, pivot through WHOIS to find who registered it:
```cypher
MATCH (h:HOSTNAME {name: "paypa1.com"})
OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
OPTIONAL MATCH (h)-[:HAS_EMAIL]->(e:EMAIL)
OPTIONAL MATCH (h)-[:REGISTERED_BY]->(o:ORGANIZATION)
RETURN r.name AS registrar, e.name AS contactEmail, o.name AS organization
```
If a contact email is shared, pivot again to find the rest of the actor's portfolio:
```cypher
MATCH (e:EMAIL {name: "email:actor@example.com"})<-[:HAS_EMAIL]-(other:HOSTNAME)
RETURN other.name AS relatedDomain LIMIT 25
```

### Step 5: Format the report

Collect the per-variant results into a JSON array and pass it to the bundled script:
```bash
python scripts/format_sweep.py --brand paypal.com --input results.json --out report
```
This writes `report.md` (a prioritized table grouped by risk tier) and `report.csv` (for ticketing or spreadsheet import). Run `python scripts/format_sweep.py --help` for the exact input schema and options. Doing the formatting in a script keeps it deterministic - do not hand-format large result sets.

### Step 6: Recommend actions

Close with a tiered action list:
- **Weaponized** (on a feed / `HIGH`+ verdict) - report for takedown now.
- **Suspicious** (registered, shared registrant with a known-bad, high-confidence method) - escalate / monitor closely.
- **Monitor** (registered, no threat signal yet) - add to the watchlist.

## Examples

### Example 1: "Find typosquats of paypal.com"

Actions:
1. `domain_variants("paypal.com")` → registered lookalikes with method + confidence.
2. `query` - the batch threat-feed screen from Step 2.
3. `explain_indicator` on each flagged variant.
4. `query` - WHOIS pivot on the worst offenders.
5. `scripts/format_sweep.py` → `report.md` + `report.csv`.

Result: A ranked report - weaponized lookalikes with feeds and registrant, suspicious ones to watch, and a takedown list.

### Example 2: "Are there any homoglyph domains impersonating our brand?"

Actions:
1. `domain_variants("acme.com")` → filter the results to `method = "HOMOGLYPH"` (confidence 0.9). Hits arrive as `xn--…` punycode.
2. `explain_indicator` on each homoglyph hit.

Result: The homoglyph subset with verdicts. Homoglyph and bitsquatting are the highest-confidence methods - treat any registered hit as suspicious even before a feed flags it.

### Example 3: "Build a watchlist of domains an attacker might register"

Actions:
1. `domain_variants` with the include-unregistered option enabled → the full generated set, not just registered nodes.
2. `scripts/format_sweep.py` with the watchlist input - no threat enrichment needed since these are not registered.

Result: A monitoring watchlist. Note clearly that these are *unregistered* - the value is pre-registering or alerting if one appears.

## Troubleshooting

### `domain_variants` returns very few or no results

By default it only returns variants that exist as graph nodes - a brand with few registered lookalikes is a *good* result. If the user wants the full generated set, enable the include-unregistered option. Confirm the input is a bare apex domain (e.g. `paypal.com`, not `https://paypal.com` or `www.paypal.com`).

### A homoglyph variant looks like gibberish (`xn--…`)

That is punycode - the ASCII-compatible encoding of a Unicode confusable domain. It is correct. The report script decodes it back to the Unicode form in the human-readable column.

### Everything comes back as "registered but not flagged"

Common and expected - most registered lookalikes are not yet on a feed. Do not dismiss them. Prioritize by `method` confidence (homoglyph and bitsquatting highest) and by shared WHOIS attribution with known-bad domains. Recommend monitoring rather than takedown.

### `format_sweep.py` errors on the input

Run `python scripts/format_sweep.py --help` and check the JSON against the documented schema. Every record needs at least a `variant` field; threat and WHOIS fields are optional and the script handles missing ones.

### The user asks for a takedown verdict on a variant the brand owns

WHOIS attribution catches this - a variant `REGISTERED_BY` the brand's own organization, or sharing the brand's contact email, is a defensive registration, not a threat. Flag it as brand-owned and exclude it from the takedown list.
