# The stable shape of WhisperGraph

What does not change: the layers, the edge directions, and which edges are computed at query time.

**No counts appear in this file, on purpose.** Label counts, edge counts and totals drift continuously,
and the published pages have disagreed with each other about them. Read magnitudes from the
`whisper://stats` resource and the label catalogue from `explain_schema`: both are cheap, both are
cached, and both are right.

## Contents

- [The layers](#the-layers)
- [Naming rules that catch everyone](#naming-rules-that-catch-everyone)
- [Edge directions that silently return nothing](#edge-directions-that-silently-return-nothing)
- [Stored versus query-time edges](#stored-versus-query-time-edges)
- [Traversal chains worth memorising](#traversal-chains-worth-memorising)
- [Introspection](#introspection)

## The layers

One connected graph, so a single query can cross from a web link to the building that routes it.

| Layer | What is in it |
|---|---|
| Physical | facilities, internet exchanges, submarine cables and their landings, CDN points of presence, cloud regions |
| Network | autonomous systems and their names, announced and allocated prefixes, BGP adjacency and path observations, RPKI ROAs and IRR route objects |
| Addressing | IPv4 and IPv6 addresses, CIDR blocks, GeoIP city and country |
| Naming and DNS | hostnames, the domain hierarchy, top-level domains and their operators, nameservers, DNSSEC, certificates and certificate transparency, DNS history through procedures |
| Ownership | organisations, registrars, WHOIS and RDAP contacts, company profiles |
| Email | mail exchangers, the SPF mechanism chain, DMARC reporting, DKIM signing, and per-domain mail posture such as DMARC policy, MTA-STS, TLS-RPT and BIMI |
| Web | hyperlinks and redirects between hosts, the technologies a host runs |
| Threat | feed sources and categories, threat signals and tags, threat actors and their ATT&CK techniques, Tor relays, TLS fingerprints, crypto wallets |

CVE IDs and file hashes are not graph labels. Assess them with `explain_indicator`.

## Naming rules that catch everyone

- **There is no `DOMAIN` label and no `FQDN` label.** Everything with a name in DNS is `HOSTNAME`:
  apexes, subdomains, nameservers and mail servers alike.
- **`.name` is the indexed property on every label**, and it carries the canonical value: the address
  for an address, the network number for a network, the CIDR string for a prefix.
- **A network's number and its name are different nodes.** `asn.name` is the number, such as `AS15169`;
  the registered network name is an `ASN_NAME` node reached by `HAS_NAME`. Filtering a network by its
  human name means filtering the name node.
- **Some labels have no `name`.** A ROA, for one, is reached from the prefix or network it covers, never
  by scanning.
- **Feed sources carry a stable identifier.** Anchor on it rather than on the display string.

## Edge directions that silently return nothing

Walking an edge backwards returns zero rows and no error. This is the single most common cause of a
query that looks right and comes back empty.

| Edge | Stored direction | To answer the natural question |
|---|---|---|
| resolution | hostname → address, **forward only** | reverse lookup is `(addr)<-[:RESOLVES_TO]-(host)` |
| nameserver | **server → domain** | a domain's nameservers are `(domain)<-[:NAMESERVER_FOR]-(ns)` |
| mail exchanger | **server → domain** | a domain's mail servers are `(domain)<-[:MAIL_FOR]-(mx)` |
| hierarchy | child → parent | a parent's children are `(parent)<-[:CHILD_OF]-(child)`; an email address is also `CHILD_OF` its domain |
| geolocation | address → city → country | `(ip)-[:LOCATED_IN]->(c:CITY)-[:HAS_COUNTRY]->(co)`; `(ip)-[:HAS_COUNTRY]->(co)` gives the country alone. From a hostname, go through its addresses: a direct country hop there is uneven |
| BGP announcement | address or prefix → **announced prefix**, never straight to the network | then `(ap)-[:ROUTES]-(a:ASN)`, which matches either arrow |
| adjacency | symmetric between networks | match `-[:BGP_NEIGHBOR]-` without a direction |
| RPKI | ROA → prefix and ROA → network | `(r:ROA)-[:ROA_AUTHORIZES_PREFIX]->(p)`; the same edges also carry IRR route objects, so filter `r.authSource = "rpki-roa"` for true ROAs |
| physical presence | network → facility, exchange → facility, cable landing → facility | anchor on the network, exchange or landing; a walk anchored on the facility does not follow every one of these back |

Two prefix edges exist and they answer different questions: `BELONGS_TO` gives the **allocated** prefix
from the registry, `ANNOUNCED_BY` gives the **BGP-announced** prefix. Use the announced one when you
intend to walk on to the routing network.

`LINKS_TO` is lopsided: the outbound side is small, and the inbound side, computed when you ask, can run
into the millions. Anchor and bound before you aggregate over inbound links.

## Stored versus query-time edges

**Stored edges** behave normally: the DNS set, the SPF mechanisms, contacts and registrars, hyperlinks
and redirects.

**Query-time edges** are computed when you ask. `explain_schema` marks each one as `virtual`. They include
the routing set, the threat and attribution set, geolocation, DMARC reporting and DKIM signing,
certificate-transparency observations, the RPKI edges and the physical-infrastructure set. One rule
follows:

**At least one endpoint must be labelled or anchored.** A fixed-length hop with both ends bare cannot be
planned and is rejected outright, which is the good case, because it tells you. Variable-length
`[*1..N]` patterns *do* follow query-time edges and return rows normally; there is no need to split them
into single hops. A `CHILD_OF` walk can climb to the top-level domain unless you stop it there.

A few edges are real and traversable but do not appear in the relationship-type listing at all, because
they are synthesised only when you anchor one end. Anchor them and they work; count them globally and
you get zero. If an edge you are sure exists is missing from the listing, try anchoring before
concluding it is gone.

TLS fingerprints have no populated edges to walk. Look a fingerprint up by its hash with
`CALL whisper.lookupTlsFingerprint([hash])`.

## Traversal chains worth memorising

```cypher
// hostname → address → announced prefix → network → network name
MATCH (h:HOSTNAME {name: $host})-[:RESOLVES_TO]->(ip:IPV4)
MATCH (ip)-[:ANNOUNCED_BY]->(ap:ANNOUNCED_PREFIX)
MATCH (ap)<-[:ROUTES]-(a:ASN)-[:HAS_NAME]->(n:ASN_NAME)
RETURN ip.name AS ip, ap.name AS prefix, a.name AS asn, n.name AS network
LIMIT 25
```

```cypher
// hostname → address → city → country
MATCH (h:HOSTNAME {name: $host})-[:RESOLVES_TO]->(ip:IPV4)
MATCH (ip)-[:LOCATED_IN]->(c:CITY)-[:HAS_COUNTRY]->(co:COUNTRY)
RETURN DISTINCT ip.name AS ip, c.displayName AS city, co.name AS country
LIMIT 25
```

```cypher
// anchored node → its threat-feed listings → the categories those feeds belong to
MATCH (ip:IPV4 {name: $ip})-[:LISTED_IN]->(f:FEED_SOURCE)
MATCH (f)-[:BELONGS_TO]->(cat:CATEGORY)
RETURN f.name AS feed, collect(DISTINCT cat.name) AS categories
LIMIT 50
```

A city's `name` is an identifier; `displayName` is the readable form. Each chain is written as separate
`MATCH` clauses rather than one long pattern. That is for readability and for cutting a wide hop with
`WITH ... LIMIT` when you need to, not because a query-time edge requires it.

## Introspection

These describe the live graph and never count against quota, so prefer them to any written-down list,
including this one.

| Call | Returns |
|---|---|
| `CALL db.labels()` | every node label with its count |
| `CALL db.relationshipTypes()` | every edge type with the labels observed on each end |
| `CALL db.propertyKeys()` | every property name in use |
| `CALL db.schema('json')` | a structured overview; also accepts `'markdown'` and `'details'` |
| `CALL db.procedures()` | every procedure, with its signature |

The relationship listing yields a column named `type`, alongside the source and target labels, a count,
and flags marking aliases and declared-but-empty types. Those flags are exactly what a drift check
wants.

From the connector, `explain_schema` wraps the same information in a form built for reading, and the
`whisper://schema/full` resource carries the property reference at once.
