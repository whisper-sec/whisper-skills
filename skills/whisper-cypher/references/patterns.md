# Patterns, indexed by question

A short, maintained set rather than a long one. Copy the closest pattern and adapt it; values are bound
as parameters, so you can pass them through the `params` argument unchanged.

CI plans every pattern here against the live graph on every change and rejects any that names a label or
edge that does not exist. That means a pattern here is never nonsense — it does **not** mean a pattern
will return useful rows for your particular input. Zero rows is a result you still have to interpret.

Blocks fenced `cypher-illustrative` are deliberately wrong and are shown to be recognised, not run.

## Contents

- [Who hosts this, and on whose network](#who-hosts-this-and-on-whose-network)
- [What else is on this address](#what-else-is-on-this-address)
- [Who registered it](#who-registered-it)
- [What else shares that registrant](#what-else-shares-that-registrant)
- [Which feeds list it, and how recently](#which-feeds-list-it-and-how-recently)
- [Subdomains](#subdomains)
- [Where does it resolve, geographically](#where-does-it-resolve-geographically)
- [Who can send mail as this domain](#who-can-send-mail-as-this-domain)
- [Nameservers and mail servers](#nameservers-and-mail-servers)
- [Do two domains share anything](#do-two-domains-share-anything)
- [Batch lookups](#batch-lookups)
- [Is this address a Tor exit](#is-this-address-a-tor-exit)
- [Routing conflicts on a network](#routing-conflicts-on-a-network)
- [Patterns that look right and are not](#patterns-that-look-right-and-are-not)

## Who hosts this, and on whose network

The canonical chain, written as separate clauses so a wide hop can be cut with `WITH ... LIMIT`.

```cypher
MATCH (h:HOSTNAME {name: $host})-[:RESOLVES_TO]->(ip:IPV4)
MATCH (ip)-[:ANNOUNCED_BY]->(ap:ANNOUNCED_PREFIX)
MATCH (ap)<-[:ROUTES]-(a:ASN)-[:HAS_NAME]->(n:ASN_NAME)
RETURN ip.name AS ip, ap.name AS prefix, a.name AS asn, n.name AS network
LIMIT 25
```

For the allocated block from the registry rather than the announced one, use `BELONGS_TO` to `PREFIX`.
They answer different questions and often differ.

## What else is on this address

Count before you enumerate — a popular address can host an enormous number of names.

```cypher
MATCH (ip:IPV4 {name: $ip})<-[:RESOLVES_TO]-(h:HOSTNAME)
RETURN count(h) AS cohostedHosts
```

Then, if the count is manageable:

```cypher
MATCH (ip:IPV4 {name: $ip})<-[:RESOLVES_TO]-(h:HOSTNAME)
RETURN h.name AS host
LIMIT 100
```

## Who registered it

Registration data is sparse and redacted. Use optional matches or a missing field drops the whole row.

```cypher
MATCH (h:HOSTNAME {name: $host})
OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
OPTIONAL MATCH (h)-[:HAS_EMAIL]->(e:EMAIL)
OPTIONAL MATCH (h)-[:REGISTERED_BY]->(o:ORGANIZATION)
RETURN r.name AS registrar, e.name AS contactEmail, o.name AS organization
LIMIT 10
```

## What else shares that registrant

The pivot that turns one bad domain into an actor's estate. A privacy service's shared address clusters
nothing — check what the address actually is before drawing a conclusion.

```cypher
MATCH (h:HOSTNAME {name: $host})-[:HAS_EMAIL]->(e:EMAIL)
MATCH (e)<-[:HAS_EMAIL]-(other:HOSTNAME)
WHERE other.name <> $host
RETURN e.name AS sharedEmail, other.name AS relatedDomain
LIMIT 50
```

## Which feeds list it, and how recently

**The listing edge carries no properties.** `firstSeen`, `lastSeen` and `weight` are all null on it, so
a query that selects them returns null columns and sorts on nothing. Recency lives on
`explain_indicator`'s `sources[]` array, one entry per feed with its own weight and timestamps — use the
tool for the "how recently" half of the question.

Cypher gives you the feed list:

```cypher
MATCH (ip:IPV4 {name: $ip})-[:LISTED_IN]->(f:FEED_SOURCE)
RETURN f.id AS feed, f.name AS displayName
LIMIT 50
```

Reach the categories by traversing on from the anchored feed, never by scanning the category label:

```cypher
MATCH (ip:IPV4 {name: $ip})-[:LISTED_IN]->(f:FEED_SOURCE)
MATCH (f)-[:BELONGS_TO]->(c:CATEGORY)
RETURN DISTINCT c.name AS category
LIMIT 25
```

## Subdomains

Traverse the hierarchy from the anchored parent. That is indexed and bounded.

```cypher
MATCH (parent:HOSTNAME {name: $apex})<-[:CHILD_OF]-(child:HOSTNAME)
RETURN child.name AS subdomain
LIMIT 200
```

A suffix scan also works, but only when the suffix is selective and carries its leading dot. A broad,
common suffix is a whole-label scan and will not finish.

```cypher
MATCH (h:HOSTNAME)
WHERE h.name ENDS WITH $dottedSuffix
RETURN h.name AS host
LIMIT 100
```

## Where does it resolve, geographically

Anycast, large CDN ranges and carrier NAT frequently have no city. No rows means no data, not a
location — read the owning network's country instead and say which you used.

```cypher
MATCH (h:HOSTNAME {name: $host})-[:RESOLVES_TO]->(ip:IPV4)
OPTIONAL MATCH (ip)-[:LOCATED_IN]->(c:CITY)-[:HAS_COUNTRY]->(co:COUNTRY)
RETURN DISTINCT ip.name AS ip, c.name AS city, co.name AS country
LIMIT 50
```

## Who can send mail as this domain

The SPF chain is stored as edges, one per mechanism, so it can be walked instead of parsed.

```cypher
MATCH (h:HOSTNAME {name: $host})-[:SPF_INCLUDE]->(inc:HOSTNAME)
RETURN inc.name AS spfInclude
LIMIT 100
```

```cypher
MATCH (h:HOSTNAME {name: $host})-[:SPF_IP]->(n)
RETURN labels(n)[0] AS kind, n.name AS authorized
LIMIT 100
```

## Nameservers and mail servers

Both edges point **server → domain**. Written the natural way round, they return nothing.

```cypher
MATCH (d:HOSTNAME {name: $host})<-[:NAMESERVER_FOR]-(ns:HOSTNAME)
RETURN ns.name AS nameserver
LIMIT 25
```

```cypher
MATCH (d:HOSTNAME {name: $host})<-[:MAIL_FOR]-(mx:HOSTNAME)
RETURN mx.name AS mailServer
LIMIT 25
```

## Do two domains share anything

The question that is hard to answer anywhere else. Anchor both ends and let the graph meet in the
middle.

```cypher
MATCH (a:HOSTNAME {name: $hostA})-[:RESOLVES_TO]->(ip:IPV4)
MATCH (ip)<-[:RESOLVES_TO]-(b:HOSTNAME {name: $hostB})
RETURN ip.name AS sharedAddress
LIMIT 25
```

```cypher
MATCH (a:HOSTNAME {name: $hostA})<-[:NAMESERVER_FOR]-(ns:HOSTNAME)
MATCH (ns)-[:NAMESERVER_FOR]->(b:HOSTNAME {name: $hostB})
RETURN ns.name AS sharedNameserver
LIMIT 25
```

## Batch lookups

Each unwound element stays an anchored lookup, so a few hundred is fast. Keep the list short when the
body of the query calls a procedure, because that is one backend call per element.

```cypher
UNWIND $hosts AS host
MATCH (h:HOSTNAME {name: host})-[:RESOLVES_TO]->(ip:IPV4)
RETURN host, collect(DISTINCT ip.name) AS addresses
LIMIT 500
```

## Is this address a Tor exit

```cypher
MATCH (ip:IPV4 {name: $ip})-[:OPERATES_EXIT_NODE]->(r:TOR_RELAY)
RETURN r.name AS relay
LIMIT 25
```

Descriptive, not accusatory. A Tor exit is a Tor exit; whether that matters is your organisation's
policy, not a verdict.

## Routing conflicts on a network

A multi-origin conflict is what a hijack looks like and also what legitimate anycast looks like. Report
the conflict; do not report a hijack.

```cypher
MATCH (a:ASN {name: $asn})-[:ROUTES]->(ap:ANNOUNCED_PREFIX)
MATCH (ap)-[:CONFLICTS_WITH]->(other:ASN)
RETURN ap.name AS prefix, other.name AS conflictingAsn
LIMIT 100
```

## Patterns that look right and are not

Each of these is a real failure mode. They are shown so they are recognisable, not to be run.

```cypher-illustrative
// WRONG: no such label. Everything named in DNS is HOSTNAME.
MATCH (d:DOMAIN {name: "example.com"}) RETURN d LIMIT 1
```

```cypher-illustrative
// WRONG: forward DNS only. This returns nothing, with no error.
MATCH (ip:IPV4 {name: "8.8.8.8"})-[:RESOLVES_TO]->(h:HOSTNAME) RETURN h LIMIT 10
```

```cypher-illustrative
// WRONG: internal ids are strings, so this comparison is null —
// the query SUCCEEDS and matches nothing. Order on an indexed property instead.
MATCH (h:HOSTNAME {name: "example.com"}) WHERE id(h) > 100 RETURN h LIMIT 10
```

```cypher-illustrative
// WRONG: scanning the feed label directly is never allowed, at any size.
MATCH (f:FEED_SOURCE)<-[:LISTED_IN]-(x) RETURN f.name, count(x)
```

```cypher-illustrative
// WRONG: the LISTED_IN edge has no properties, so all three columns come back null
// and the sort orders on nothing. Read sources[] from explain_indicator instead.
MATCH (ip:IPV4 {name: "8.8.8.8"})-[l:LISTED_IN]->(f:FEED_SOURCE)
RETURN f.id, l.firstSeen, l.lastSeen ORDER BY l.lastSeen DESC LIMIT 10
```

```cypher-illustrative
// WRONG: a whole-graph aggregate touches every edge and will not finish.
MATCH ()-[r]->() RETURN count(r)
```
