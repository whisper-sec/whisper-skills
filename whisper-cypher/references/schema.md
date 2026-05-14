# WhisperGraph Schema Reference

Counts are recent snapshots. For live numbers call the `list_labels` MCP tool or `CALL db.labels()`.

## Node labels (20)

| Label | Count | Description | Example `.name` |
|-------|------:|-------------|-----------------|
| HOSTNAME | 2.63B | Any fully-qualified hostname - apex, subdomain, nameserver, mail server | `www.google.com` |
| IPV4 | 619M | IPv4 address | `142.250.64.100` |
| IPV6 | 820K | IPv6 address (zero-padded form) | `2606:4700:4700:0000:0000:0000:0000:1111` |
| PREFIX | 2.49M | IP prefix / CIDR block | `142.250.64.0/24` |
| ASN | 116K | Autonomous system number | `AS15169` |
| ASN_NAME | 108K | Autonomous system descriptive name | `GOOGLE` |
| TLD | 1,743 | Top-level domain | `com` |
| CITY | 54K | City (GeoIP) | `Mountain View, US` |
| COUNTRY | 424 | ISO country codes + RIR special codes | `US` |
| RIR | 5 | Regional Internet Registry | `ARIN` |
| ORGANIZATION | 119M | Org entity (RIR handles + WHOIS registrants) | `cloudflare, inc.` |
| TLD_OPERATOR | 737 | TLD registry operator | `VeriSign` |
| REGISTRAR | 51K | Domain registrar (WHOIS) | `registrar:markmonitor inc.` |
| EMAIL | 237M | Contact email (WHOIS) | `email:dns-admin@google.com` |
| PHONE | 60M | Contact phone (WHOIS, E.164) | `+16502530000` |
| DNSSEC_ALGORITHM | 8 | DNSSEC signing algorithm | `ECDSAP256SHA256` |
| REGISTERED_PREFIX | 326K | RIR-allocated prefix (owner view; **virtual**) | `8.8.8.0/24` |
| ANNOUNCED_PREFIX | 1.40M | BGP-announced prefix (routing view; **virtual**) | `1.0.0.0/24` |
| FEED_SOURCE | 40 | Threat-intel feed source (**virtual**) | `Dan Tor Exit` |
| CATEGORY | 18 | Threat category (**virtual**) | `C2 Servers` |

Every node has a `.name` string property - it is the indexed property on every label. There is **no `DOMAIN` or `FQDN` label**; everything domain-shaped is `HOSTNAME`.

**Virtual labels** (`FEED_SOURCE`, `CATEGORY`, `REGISTERED_PREFIX`, `ANNOUNCED_PREFIX`) are synthesized by the threat-intel and BGP enrichment layers. Access them via edge traversal from anchored nodes - never scan them directly.

**Labels safe to scan unanchored** (small): `COUNTRY`, `RIR`, `TLD`, `TLD_OPERATOR`, `DNSSEC_ALGORITHM`, `CATEGORY`. Everything else must be anchored. `FEED_SOURCE` is *not* in this list - it is virtual and scanning it times out.

## Physical edge types (24)

| Edge | Source → Target | Notes |
|------|-----------------|-------|
| CHILD_OF | HOSTNAME, EMAIL → HOSTNAME, TLD | DNS hierarchy; child → parent |
| RESOLVES_TO | HOSTNAME → IPV4/IPV6 | DNS A/AAAA - **forward only**, no reverse-PTR |
| BELONGS_TO | IPV4, IPV6, PREFIX, FEED_SOURCE → PREFIX, RIR, CATEGORY | IP→prefix, prefix→RIR, feed→category |
| NAMESERVER_FOR | HOSTNAME, TLD → HOSTNAME | NS record; nameserver → domain it serves |
| MAIL_FOR | HOSTNAME, TLD → HOSTNAME | MX record; mail server → domain it serves |
| LINKS_TO | HOSTNAME → HOSTNAME | Web hyperlink (Common Crawl) |
| ALIAS_OF | HOSTNAME → HOSTNAME | CNAME |
| SPF_INCLUDE | HOSTNAME → HOSTNAME, TLD | SPF `include:` |
| SPF_IP | HOSTNAME → IPV4, IPV6, PREFIX | SPF `ip4:`/`ip6:` (filtering on `:IPV4` alone undercounts) |
| SPF_A | HOSTNAME → HOSTNAME | SPF `a:` |
| SPF_MX | HOSTNAME → HOSTNAME | SPF `mx:` |
| SPF_EXISTS | HOSTNAME → HOSTNAME | SPF `exists:` |
| SPF_REDIRECT | HOSTNAME → HOSTNAME | SPF `redirect=` |
| HAS_COUNTRY | ASN, CITY, IPV4, HOSTNAME, PHONE, ANNOUNCED_PREFIX, REGISTERED_PREFIX → COUNTRY | Country association |
| REGISTERED_BY | HOSTNAME, ASN, PREFIX → ORGANIZATION | Org registration (WHOIS + RIR) |
| LOCATED_IN | IPV4, IPV6 → CITY | GeoIP - IP→CITY **only**; chain `HAS_COUNTRY` for country |
| OPERATES | TLD_OPERATOR → TLD | TLD registry operator |
| HAS_REGISTRAR | HOSTNAME → REGISTRAR | Current registrar (WHOIS) |
| HAS_EMAIL | HOSTNAME → EMAIL | Domain contact email (WHOIS) |
| HAS_PHONE | HOSTNAME → PHONE | Domain contact phone (WHOIS) |
| PREV_REGISTRAR | HOSTNAME → REGISTRAR | Historical registrar (WHOIS) |
| ANNOUNCED_BY | IPV4, IPV6 → ANNOUNCED_PREFIX | BGP announcement - target is the prefix, **not** the ASN |
| LISTED_IN | IPV4, IPV6, HOSTNAME → FEED_SOURCE | Threat indicator on a feed |
| CONFLICTS_WITH | PREFIX, ANNOUNCED_PREFIX → ASN | MOAS conflict (bidirectional) |

## Virtual edge types (5)

Synthesized at query time - they work in anchored queries but do not appear in `CALL db.relationshipTypes()`.

| Edge | Source → Target | Notes |
|------|-----------------|-------|
| HAS_NAME | ASN → ASN_NAME | `asn.name` is the AS number; the network name is on the ASN_NAME node |
| ROUTES | ANNOUNCED_PREFIX, ASN → ASN, PREFIX | ASN routes prefix via BGP |
| PEERS_WITH | ASN ↔ ASN | BGP peering (bidirectional) |
| SIGNED_WITH | HOSTNAME → DNSSEC_ALGORITHM | DNSSEC DS record - **currently empty on live data**, returns 0 |
| PARENT_OF | TLD, HOSTNAME → HOSTNAME | Reverse of CHILD_OF |

## Edge-direction landmines (most common 0-result causes)

| Wrong | Right |
|-------|-------|
| `(ip:IPV4)-[:ANNOUNCED_BY]->(:ASN)` | `(ip)-[:ANNOUNCED_BY]->(:ANNOUNCED_PREFIX)-[:ROUTES]->(:ASN)` |
| `(:IPV4)-[:LOCATED_IN]->(:COUNTRY)` | `(:IPV4)-[:LOCATED_IN]->(:CITY)-[:HAS_COUNTRY]->(:COUNTRY)` |
| `(domain)-[:MAIL_FOR]->(mx)` | `(domain)<-[:MAIL_FOR]-(mx)` |
| `(domain)-[:NAMESERVER_FOR]->(ns)` | `(domain)<-[:NAMESERVER_FOR]-(ns)` |
| `(:IPV4)-[:RESOLVES_TO]->(:HOSTNAME)` | `(:IPV4)<-[:RESOLVES_TO]-(:HOSTNAME)` |
| `(parent)-[:CHILD_OF]->(child)` | `(child)-[:CHILD_OF]->(parent)` |
| `(ip)-[:BELONGS_TO]->(:RIR)` | `(ip)-[:BELONGS_TO]->(:PREFIX)-[:BELONGS_TO]->(:RIR)` |
| `RETURN asn.name` for the network name | `(asn)-[:HAS_NAME]->(n:ASN_NAME) RETURN n.name` |
| `(asn:ASN)-[:ROUTES]->(p:ANNOUNCED_PREFIX)` | `(asn:ASN)<-[:ROUTES]-(p:ANNOUNCED_PREFIX)` |
| `(asn:ASN)-[:CONFLICTS_WITH]->(p)` | `(asn:ASN)<-[:CONFLICTS_WITH]-(p:ANNOUNCED_PREFIX)` |

## Threat-intelligence properties

Present on `IPV4` / `IPV6` / `HOSTNAME` nodes that are listed in any feed:

`threatScore` (Double), `threatLevel` (String: NONE/INFO/LOW/MEDIUM/HIGH/CRITICAL), `threatSources` (Long, feed count), `threatFirstSeen` / `threatLastSeen` (Long, epoch ms), and booleans: `isThreat`, `isAnonymizer`, `isC2`, `isMalware`, `isPhishing`, `isSpam`, `isBruteforce`, `isScanner`, `isBlacklist`, `isTor`, `isProxy`, `isVpn`, `isWhitelist`.

**ANNOUNCED_PREFIX** carries BGP enrichment: `isMoas`, `isAnycast`, `isWithdrawn`, `wasMoas`, `hasOriginChanged` (Booleans), `threatScore`, `threatLevel`, `threatSourceCount`, `firstSeen`, `lastSeen`.

**ASN** carries `threatScore` and `threatLevel` (max / overall across hosted IPs).

**LISTED_IN edge** carries `firstSeen`, `lastSeen` (epoch seconds), `weight` (Float, feed confidence).

## Canonical traversal chains

```
DNS resolution:  HOSTNAME -[:RESOLVES_TO]-> IPV4 -[:BELONGS_TO]-> PREFIX <-[:ROUTES]- ASN -[:HAS_NAME]-> ASN_NAME
DNS hierarchy:   HOSTNAME -[:CHILD_OF]-> HOSTNAME -[:CHILD_OF]-> TLD
GeoIP:           IPV4 -[:LOCATED_IN]-> CITY -[:HAS_COUNTRY]-> COUNTRY
BGP (direct):    IPV4 -[:ANNOUNCED_BY]-> ANNOUNCED_PREFIX -[:ROUTES]-> ASN
BGP (routing):   ASN -[:ROUTES]-> PREFIX ;  ASN -[:PEERS_WITH]-> ASN
WHOIS:           HOSTNAME -[:HAS_REGISTRAR|HAS_EMAIL|HAS_PHONE|REGISTERED_BY]-> REGISTRAR|EMAIL|PHONE|ORGANIZATION
Threat intel:    IPV4|IPV6|HOSTNAME -[:LISTED_IN]-> FEED_SOURCE -[:BELONGS_TO]-> CATEGORY
```

## Introspection and procedures

| Call | Returns |
|------|---------|
| `CALL db.labels()` | All node labels with counts |
| `CALL db.relationshipTypes()` | All physical edge types with counts |
| `CALL db.propertyKeys()` | All property keys |
| `CALL db.schema.nodeTypeProperties()` | Property metadata per node type |
| `CALL db.schema("json")` | Full schema as JSON (also: `cypher`, `markdown`, `details`) |
| `CALL explain("indicator")` | Threat assessment for IP / domain / ASN / CIDR |
| `CALL whisper.history("indicator")` | Historical WHOIS / BGP snapshots |
| `CALL whisper.variants("name" [, "LABEL"] [, checkExisting])` | Typosquatting variants (14 algorithms) |
| `CALL whisper.quota()` | Plan tier, rate limits, usage, max query depth |
| `EXPLAIN <query>` | Query plan without executing |
| `PROFILE <query>` | Execute and report per-operator timing |

The `explain`, `whisper.history`, and `whisper.variants` procedures are also exposed as dedicated MCP tools (`explain_indicator`, `whisper_history`, `domain_variants`) - prefer the tools; they are cheaper and more authoritative than hand-walking the graph.

## Supported functions (quick list)

- **Aggregation**: `count`, `count(DISTINCT …)`, `sum`, `avg`, `min`, `max`, `collect`, `stdev`, `percentile_disc`, `percentile_cont`
- **String**: `toUpper`, `toLower`, `trim`, `replace`, `substring`, `split`, `left`, `right`, `size`, `reverse`, `toString`
- **Numeric**: `abs`, `ceil`, `floor`, `round`, `sqrt`, `log`, `log10`, `exp`, `sign`, `rand`
- **Collection**: `head`, `last`, `tail`, `range`, `coalesce`, `isEmpty`, `keys`, `reduce`
- **List predicates**: `all`, `any`, `none`, `single`
- **Path / node**: `labels`, `type`, `nodes`, `relationships`, `length`, `startNode`, `endNode`, `id`, `elementId`
- **Geospatial**: `point(...)`, `distance(p1, p2)`, `point.distance(p1, p2)`
- **Date/time**: `timestamp()`, `datetime()`, `date()`, `duration(...)`, `duration.between(...)`
- **Type conversion**: `toInteger`, `toFloat`, `toBoolean`, `toString` (+ `*List` variants)
