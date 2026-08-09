# The stable shape of WhisperGraph

What does not change: the layers, the edge directions, and the physical-versus-query-time distinction.

**No counts appear in this file, on purpose.** Label counts, edge counts and totals drift continuously,
and the published pages have disagreed with each other about them. Read magnitudes from the
`whisper://stats` resource and the label catalogue from `explain_schema` — both are cheap, both are
cached, and both are right.

## Contents

- [The layers](#the-layers)
- [Naming rules that catch everyone](#naming-rules-that-catch-everyone)
- [Edge directions that silently return nothing](#edge-directions-that-silently-return-nothing)
- [Physical versus query-time edges](#physical-versus-query-time-edges)
- [Traversal chains worth memorising](#traversal-chains-worth-memorising)
- [Introspection](#introspection)

## The layers

One connected graph, so a single query can cross from a web link to the building that routes it.

| Layer | What is in it |
|---|---|
| Physical | facilities, internet exchanges, submarine cables and their landings, CDN points of presence, cloud regions |
| Network | autonomous systems, announced and allocated prefixes, BGP adjacency, RPKI authorisations |
| Addressing | IPv4 and IPv6 addresses, CIDR blocks, GeoIP city and country |
| Naming and DNS | hostnames, the domain hierarchy, top-level domains, nameservers, DNSSEC, certificate transparency |
| Ownership | organisations, registrars, WHOIS and RDAP contact email and phone |
| Email | mail exchangers, the full SPF mechanism chain, DMARC reporting, DKIM signing vendors |
| Web | hyperlinks between hosts |
| Threat | feed sources and categories, threat signals, actors and their techniques, Tor relays, TLS fingerprints |

## Naming rules that catch everyone

- **There is no `DOMAIN` label and no `FQDN` label.** Everything with a name in DNS is `HOSTNAME` —
  apexes, subdomains, nameservers, mail servers alike.
- **`.name` is the indexed property on every label**, and it carries the canonical value: the address
  for an address, the network number for a network, the CIDR string for a prefix.
- **A network's number and its name are different nodes.** The number lives on the autonomous-system
  node; the registered network name is a separate node reached by an edge. Filtering a network by its
  human name means filtering the name node, not the number node.
- **Feed sources carry a stable slug.** Anchor on the identifier rather than the display string.

## Edge directions that silently return nothing

Walking an edge backwards returns zero rows and no error. This is the single most common cause of a
query that looks right and comes back empty.

| Edge | Stored direction | To answer the natural question |
|---|---|---|
| resolution | hostname → address, **forward only** | reverse lookup is `(addr)<-[:RESOLVES_TO]-(host)` |
| nameserver | **server → domain** | a domain's nameservers are `(domain)<-[:NAMESERVER_FOR]-(ns)` |
| mail exchanger | **server → domain** | a domain's mail servers are `(domain)<-[:MAIL_FOR]-(mx)` |
| hierarchy | child → parent | a parent's children are `(parent)<-[:CHILD_OF]-(child)` |
| geolocation | address → city | chain on to the country; there is no direct address-to-country hop for a city-mapped address |
| BGP announcement | address → **announced prefix**, not straight to the network | traverse announced prefix → network |
| adjacency | symmetric between networks | matches in either direction |

Two prefix edges exist and they answer different questions: one gives the **allocated** prefix from the
registry, the other gives the **BGP-announced** prefix. Use the announced one when you intend to walk on
to the routing network.

## Physical versus query-time edges

**Physical edges** are stored on disk — the DNS set, geolocation, the SPF mechanisms, most of the
ownership set, address-to-allocated-prefix, and network adjacency. They behave normally.

**Query-time edges** are computed when you ask. That includes the routing set, the entire threat and
attribution set, DMARC and DKIM and TLS fingerprints, certificate-transparency observations, and the
physical-infrastructure set. One rule follows:

**At least one endpoint must be labelled or anchored.** A fixed-length hop with both ends bare cannot be
planned and is rejected outright — which is the good case, because it tells you. Variable-length
`[*1..N]` patterns *do* follow query-time edges and return rows normally; there is no need to split them
into single hops, and a widely repeated claim to the contrary is wrong.

A few edges are real and traversable but do not appear in the relationship-type listing at all, because
they are synthesised only when you anchor one end. Anchor them and they work; count them globally and
you get zero. If an edge you are sure exists is missing from the listing, try anchoring before
concluding it is gone.

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
RETURN DISTINCT ip.name AS ip, c.name AS city, co.name AS country
LIMIT 25
```

```cypher
// anchored node → its threat-feed listings → the categories those feeds belong to
MATCH (ip:IPV4 {name: $ip})-[:LISTED_IN]->(f:FEED_SOURCE)
MATCH (f)-[:BELONGS_TO]->(cat:CATEGORY)
RETURN f.name AS feed, collect(DISTINCT cat.name) AS categories
LIMIT 50
```

Each chain is written as separate `MATCH` clauses rather than one long pattern. That is for
readability and for cutting a wide hop with `WITH ... LIMIT` when you need to — not because a
query-time edge requires it.

## Introspection

These describe the live graph and never count against quota, so prefer them to any written-down list —
including this one.

| Call | Returns |
|---|---|
| `CALL db.labels()` | every node label with its count |
| `CALL db.relationshipTypes()` | every edge type with the labels observed on each end |
| `CALL db.propertyKeys()` | every property name in use |
| `CALL db.schema('json')` | a structured overview; also accepts `'markdown'` and `'details'` |

The relationship listing yields a column named `type`, alongside the source and target labels, a count,
and flags marking aliases and declared-but-empty types. Those flags are exactly what a drift check
wants.

From the connector, `explain_schema` wraps the same information in a form built for reading, and the
full schema resource carries the whole reference at once.
