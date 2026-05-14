# WhisperGraph Query Cookbook

Validated query patterns, organized by analyst persona. Every query here has been run against live WhisperGraph data - if a pattern is not here, it may not work. Submit these through the `query` MCP tool. Find the closest pattern to the user's question, copy it, and change the anchor value.

Conventions used throughout:
- Every example anchors on an indexed lookup (`{name: "..."}`) or a small label.
- Every row-returning query has a `LIMIT` ≤ 500. Aggregations are exempt.
- Edge directions are strict - see `schema.md` if a query returns 0 rows.

---

## SOC analysts and incident responders

```cypher
-- Trace an IP to its network owner
MATCH (ip:IPV4 {name: "104.16.123.96"})-[:BELONGS_TO]->(p:PREFIX)
      <-[:ROUTES]-(a:ASN)-[:HAS_NAME]->(n:ASN_NAME)
RETURN ip.name, p.name AS prefix, a.name AS asn, n.name AS network
```

```cypher
-- Which feeds list this IP, and what is its threat profile?
MATCH (ip:IPV4 {name: "185.220.101.1"})-[:LISTED_IN]->(f:FEED_SOURCE)
RETURN f.name, ip.threatScore, ip.threatLevel, ip.threatSources,
       ip.isThreat, ip.isC2, ip.isMalware, ip.isPhishing, ip.isTor, ip.isProxy
```

```cypher
-- Reverse DNS: what hostnames resolve to this IP?
MATCH (ip:IPV4 {name: "104.16.123.96"})<-[:RESOLVES_TO]-(h:HOSTNAME)
RETURN h.name LIMIT 25
```

```cypher
-- Co-hosted domain count - count first, then decide whether to enumerate
MATCH (ip:IPV4 {name: "104.16.123.96"})<-[:RESOLVES_TO]-(h:HOSTNAME)
RETURN count(h) AS cohostedDomains
```

```cypher
-- GeoIP: where is this IP physically located?
MATCH (ip:IPV4 {name: "8.8.8.8"})-[:LOCATED_IN]->(city:CITY)-[:HAS_COUNTRY]->(country:COUNTRY)
RETURN city.name AS city, country.name AS country
```

```cypher
-- Quick WHOIS profile for a flagged domain
MATCH (h:HOSTNAME {name: "google.com"})
OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
OPTIONAL MATCH (h)-[:HAS_EMAIL]->(e:EMAIL)
OPTIONAL MATCH (h)-[:REGISTERED_BY]->(org:ORGANIZATION)
RETURN h.name, r.name AS registrar, e.name AS contact, org.name AS organization
```

```cypher
-- Batch IOC enrichment - resolve a small list of hostnames in one call
UNWIND ["google.com", "cloudflare.com", "github.com"] AS host
MATCH (h:HOSTNAME {name: host})-[:RESOLVES_TO]->(ip:IPV4)
RETURN h.name, collect(ip.name) AS ips
```

For a one-shot threat verdict, prefer `CALL explain("185.220.101.1")` or the `explain_indicator` MCP tool over manual feed walks.

---

## Threat intelligence analysts

```cypher
-- Pivot on shared registrant email (the most reliable WHOIS pivot)
MATCH (h:HOSTNAME {name: "cloudflare.com"})-[:HAS_EMAIL]->(e:EMAIL)<-[:HAS_EMAIL]-(other:HOSTNAME)
WHERE other.name <> "cloudflare.com"
RETURN e.name AS sharedEmail, other.name AS relatedDomain LIMIT 25
```

```cypher
-- Nameserver clustering: domains sharing the same NS
MATCH (h:HOSTNAME {name: "cloudflare.com"})<-[:NAMESERVER_FOR]-(ns:HOSTNAME)-[:NAMESERVER_FOR]->(other:HOSTNAME)
WHERE other.name <> "cloudflare.com"
RETURN ns.name AS nameserver, other.name AS clusteredDomain LIMIT 25
```

```cypher
-- Threat profile of the ASN hosting a hostname
MATCH (h:HOSTNAME {name: "kaveh.org"})-[:RESOLVES_TO]->(ip:IPV4)
      -[:BELONGS_TO]->(p:PREFIX)<-[:ROUTES]-(a:ASN)
RETURN h.name, ip.name, a.name, a.threatScore, a.threatLevel
```

```cypher
-- SPF authorization graph: which mechanisms does this domain use?
-- (when matching multi-type edges, bind the relationship variable with r:)
MATCH (h:HOSTNAME {name: "cloudflare.com"})-[r:SPF_INCLUDE|SPF_A|SPF_MX|SPF_REDIRECT]->(target)
RETURN type(r) AS mechanism, target.name LIMIT 25
```

```cypher
-- Find ASN_NAMEs starting with a brand keyword (indexed prefix scan - fast)
MATCH (n:ASN_NAME) WHERE n.name STARTS WITH "GOOGLE"
RETURN n.name LIMIT 25
```

For ASN / CIDR reputation use `CALL explain("AS13335")` / `CALL explain("1.1.1.0/24")`, and `CALL whisper.history("google.com")` for WHOIS history.

---

## Penetration testers and red teams

```cypher
-- Subdomain enumeration via indexed suffix scan
MATCH (h:HOSTNAME) WHERE h.name ENDS WITH ".target.com"
RETURN h.name LIMIT 100
```

```cypher
-- Subdomain count first - avoid enumeration if there are too many
MATCH (h:HOSTNAME) WHERE h.name ENDS WITH ".google.com"
RETURN count(h) AS subdomainCount
```

```cypher
-- Co-hosted neighbours on the same prefix (lateral surface)
MATCH (h:HOSTNAME {name: "kaveh.org"})-[:RESOLVES_TO]->(ip:IPV4)
      -[:BELONGS_TO]->(p:PREFIX)<-[:BELONGS_TO]-(neighbour:IPV4)
WHERE neighbour <> ip
RETURN p.name AS prefix, neighbour.name AS sharedSubnetIP LIMIT 25
```

```cypher
-- Mail server inventory (MX is on the source side - reversed edge)
MATCH (h:HOSTNAME {name: "google.com"})<-[:MAIL_FOR]-(mx:HOSTNAME)
RETURN mx.name LIMIT 25
```

```cypher
-- SPF authorized IP space - which IPs are pre-authorized to send mail?
MATCH (h:HOSTNAME {name: "cloudflare.com"})-[:SPF_IP]->(ip)
RETURN ip.name LIMIT 25
```

```cypher
-- Hostnames discoverable via web links (Common Crawl)
MATCH (h:HOSTNAME {name: "github.com"})-[:LINKS_TO]->(target:HOSTNAME)
RETURN target.name LIMIT 25
```

---

## Brand protection and anti-phishing teams

The `whisper.variants()` procedure (and the `domain_variants` MCP tool) is the purpose-built starting point - 14 mutation algorithms, returns only registered variants by default.

```cypher
-- Registered typosquats of a brand (default - existing variants only)
CALL whisper.variants("google.com")
```

```cypher
-- Registered lookalikes enriched with threat intel - which are weaponized?
CALL whisper.variants("paypal.com") YIELD variant, method, exists, confidence
WHERE exists = true
WITH variant, method, confidence ORDER BY confidence DESC LIMIT 50
MATCH (h:HOSTNAME {name: variant})
OPTIONAL MATCH (h)-[:LISTED_IN]->(f:FEED_SOURCE)
RETURN h.name, method, confidence, h.threatLevel, h.threatScore, collect(f.name) AS feeds
ORDER BY h.threatScore DESC
```

```cypher
-- Brand-name substring search (fallback for any host containing the brand)
MATCH (h:HOSTNAME) WHERE h.name CONTAINS "google"
RETURN h.name LIMIT 25
```

```cypher
-- Hostnames that LINK_TO a brand (potential impersonation)
MATCH (h:HOSTNAME)-[:LINKS_TO]->(brand:HOSTNAME {name: "github.com"})
RETURN h.name LIMIT 25
```

```cypher
-- From a known contact email, find every domain registered with it
MATCH (e:EMAIL {name: "email:dns-admin@google.com"})<-[:HAS_EMAIL]-(h:HOSTNAME)
RETURN e.name AS contact, h.name AS domain LIMIT 25
```

---

## DNS and email security engineers

```cypher
-- Nameserver inventory for a domain
MATCH (h:HOSTNAME {name: "cloudflare.com"})<-[:NAMESERVER_FOR]-(ns:HOSTNAME)
RETURN ns.name LIMIT 25
```

```cypher
-- Full SPF mechanism audit
MATCH (h:HOSTNAME {name: "cloudflare.com"})-[r:SPF_INCLUDE|SPF_IP|SPF_A|SPF_MX|SPF_EXISTS|SPF_REDIRECT]->(target)
RETURN type(r) AS mechanism, count(target) AS occurrences
ORDER BY occurrences DESC
```

```cypher
-- Domain hierarchy: parent domains and their TLD
MATCH (h:HOSTNAME {name: "www.google.com"})-[:CHILD_OF*1..3]->(parent)
RETURN labels(parent)[0] AS labelType, parent.name AS name
```

```cypher
-- Batch nameserver audit
UNWIND ["google.com", "cloudflare.com", "github.com"] AS domain
MATCH (h:HOSTNAME {name: domain})<-[:NAMESERVER_FOR]-(ns:HOSTNAME)
RETURN h.name, collect(ns.name) AS nameservers
```

```cypher
-- What TLDs does a registry operate? (anchor on the operator - reverse times out)
MATCH (op:TLD_OPERATOR {name: "VeriSign Global Registry Services"})-[:OPERATES]->(t:TLD)
RETURN t.name LIMIT 5
```

---

## Network and BGP security engineers

```cypher
-- ASN profile - name + country in one go
MATCH (a:ASN {name: "AS15169"})-[:HAS_NAME]->(n:ASN_NAME)
MATCH (a)-[:HAS_COUNTRY]->(c:COUNTRY)
RETURN a.name, n.name AS networkName, c.name AS country
```

```cypher
-- ASN scale - prefix count and peer count
MATCH (a:ASN {name: "AS15169"})-[:ROUTES]->(p:PREFIX)
RETURN count(p) AS prefixCount
```

```cypher
-- BGP peer list (sample)
MATCH (a:ASN {name: "AS13335"})-[:PEERS_WITH]->(peer:ASN)
RETURN peer.name LIMIT 25
```

```cypher
-- IP -> BGP-announced prefix -> ASN (the BGP-direct chain)
MATCH (ip:IPV4 {name: "8.8.8.8"})-[:ANNOUNCED_BY]->(p:ANNOUNCED_PREFIX)-[:ROUTES]->(a:ASN)
RETURN ip.name, p.name AS announcedPrefix, a.name AS asn
```

```cypher
-- BGP enrichment - is this prefix MOAS / anycast / withdrawn?
MATCH (ip:IPV4 {name: "8.8.8.8"})-[:ANNOUNCED_BY]->(p:ANNOUNCED_PREFIX)
RETURN p.name, p.isMoas, p.isAnycast, p.isWithdrawn, p.wasMoas,
       p.hasOriginChanged, p.threatScore, p.threatLevel
```

```cypher
-- MOAS conflicts involving an ASN
MATCH (a:ASN {name: "AS15169"})<-[:CONFLICTS_WITH]-(p:ANNOUNCED_PREFIX)
WHERE p.isMoas = true
RETURN p.name AS prefix, p.isMoas, p.wasMoas, p.hasOriginChanged LIMIT 25
```

---

## Compliance and risk-assessment teams

```cypher
-- Country exposure for a domain (via IP geolocation - the reliable path)
MATCH (h:HOSTNAME {name: "cloudflare.com"})-[:RESOLVES_TO]->(ip:IPV4)
      -[:LOCATED_IN]->(city:CITY)-[:HAS_COUNTRY]->(country:COUNTRY)
RETURN ip.name, city.name AS city, country.name AS country LIMIT 25
```

```cypher
-- Historical registrar (changes over time)
MATCH (h:HOSTNAME {name: "google.com"})-[:PREV_REGISTRAR]->(r:REGISTRAR)
RETURN r.name AS previousRegistrar LIMIT 10
```

```cypher
-- Full security profile in one call
MATCH (h:HOSTNAME {name: "cloudflare.com"})
OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
OPTIONAL MATCH (h)-[:HAS_EMAIL]->(e:EMAIL)
OPTIONAL MATCH (h)-[:HAS_PHONE]->(p:PHONE)
OPTIONAL MATCH (h)-[:REGISTERED_BY]->(org:ORGANIZATION)
RETURN h.name, r.name AS registrar, e.name AS email, p.name AS phone, org.name AS organization
```

```cypher
-- Batch domain audit - registrar + organization for a portfolio
UNWIND ["google.com", "cloudflare.com", "github.com"] AS domain
MATCH (h:HOSTNAME {name: domain})
OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
OPTIONAL MATCH (h)-[:REGISTERED_BY]->(org:ORGANIZATION)
RETURN h.name, r.name AS registrar, org.name AS organization
```

---

## Security researchers and academics

```cypher
-- Schema introspection
CALL db.labels()
CALL db.relationshipTypes()
CALL db.schema("json")
```

```cypher
-- Threat feed catalog (40 feeds - LIMIT still required by the validator)
MATCH (f:FEED_SOURCE) RETURN f.name, f.id LIMIT 50
```

```cypher
-- Regional Internet Registries (5 total - a safe label scan)
MATCH (r:RIR) RETURN r.name LIMIT 10
```

```cypher
-- ASN peering degree for a hub network
MATCH (a:ASN {name: "AS3356"})-[:PEERS_WITH]->(peer:ASN)
RETURN count(peer) AS peeringDegree
```

```cypher
-- Shortest path between two hostnames (bounded depth required)
MATCH (a:HOSTNAME {name: "cloudflare.com"}), (b:HOSTNAME {name: "google.com"})
MATCH p = shortestPath((a)-[*1..6]-(b))
RETURN length(p) AS hops, [n IN nodes(p) | n.name] AS path
```

---

## Performance expectations

| Operation | Typical time |
|-----------|--------------|
| Anchored single-property lookup `{name: "..."}` | < 5 ms |
| 2-3 hop traversal from an anchored node | 5-50 ms |
| `CALL explain()` for IP / domain / network | 3-25 ms |
| `CALL explain()` for an ASN | up to ~80 ms |
| `CALL whisper.history()` for IP / prefix / domain | ~1-10 ms (may return `available:false`) |
| `CALL whisper.history()` for a large ASN | ~9 s |
| `CALL whisper.variants()` (default existing-only) | < 30 ms |
| Unanchored scan of HOSTNAME / IPV4 / PREFIX | timeout - rejected by the validator |

If an anchored query is slower than these numbers, the anchor is too weak - tighten the `WHERE` or reduce hop count. Use `PROFILE <query>` to see per-operator timing.
