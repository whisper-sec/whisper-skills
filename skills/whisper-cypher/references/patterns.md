# Patterns, indexed by question

A short, maintained set rather than a long one. Copy the closest pattern and adapt it; values are bound
as parameters, so you can pass them through the `params` argument unchanged.

CI plans every pattern here against the live graph on every change and rejects any that names a label or
edge that does not exist. That means a pattern here is never nonsense. It does **not** mean a pattern
will return useful rows for your particular input: zero rows is a result you still have to interpret.

Blocks fenced `cypher-illustrative` are deliberately wrong and are shown to be recognised, not run.

## Contents

- [Who hosts this, and on whose network](#who-hosts-this-and-on-whose-network)
- [What else is on this address](#what-else-is-on-this-address)
- [Which feeds list it, and how recently](#which-feeds-list-it-and-how-recently)
- [Threat context: tags, actors and techniques](#threat-context-tags-actors-and-techniques)
- [Is this URL dangerous](#is-this-url-dangerous)
- [Subdomains](#subdomains)
- [What it resolved to before](#what-it-resolved-to-before)
- [Where does it resolve, geographically](#where-does-it-resolve-geographically)
- [Nameservers and mail servers](#nameservers-and-mail-servers)
- [Mail posture](#mail-posture)
- [Who can send mail as this domain](#who-can-send-mail-as-this-domain)
- [Do two domains share anything](#do-two-domains-share-anything)
- [Batch lookups](#batch-lookups)
- [Routing: neighbours, RPKI and history](#routing-neighbours-rpki-and-history)
- [Physical presence of a network](#physical-presence-of-a-network)
- [Is this address a Tor exit](#is-this-address-a-tor-exit)
- [Who registered it](#who-registered-it)
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

Count before you enumerate: a popular address can host an enormous number of names.

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

## Which feeds list it, and how recently

The listing edge carries `firstSeen` and `lastSeen`, as epoch milliseconds, and the feed's `weight`. A
sighting from years ago and one from this morning are different findings.

```cypher
MATCH (ip:IPV4 {name: $ip})-[l:LISTED_IN]->(f:FEED_SOURCE)
RETURN f.name AS feed, l.firstSeen AS firstSeen, l.lastSeen AS lastSeen, l.weight AS weight
ORDER BY l.lastSeen DESC
LIMIT 50
```

Reach the categories by traversing on from the anchored feed, never by scanning the category label:

```cypher
MATCH (ip:IPV4 {name: $ip})-[:LISTED_IN]->(f:FEED_SOURCE)
MATCH (f)-[:BELONGS_TO]->(c:CATEGORY)
RETURN DISTINCT c.name AS category
LIMIT 25
```

For a verdict, rather than a list of listings, use `explain_indicator`: it weighs the feeds and qualifies
the result with its coverage.

## Threat context: tags, actors and techniques

One procedure call returns the feeds, tags, threat signals, attributed actors and ATT&CK techniques for
an indicator, with its own coverage field.

```cypher
CALL whisper.context($indicator)
YIELD indicator, found, tags, actors, techniques, coverage
RETURN indicator, found, tags, actors, techniques, coverage
LIMIT 5
```

`found: false` means the graph has no record of the indicator, not that it is clean. `coverage` is
reported per layer: a layer marked `none` or `sparse` holds too little for its empty list to mean
anything.

## Is this URL dangerous

A hostname verdict says nothing about one path under it. `whisper.assessUrl` scores the path and the apex
separately. Read `path_coverage` before `path_band`.

```cypher
CALL whisper.assessUrl([$url])
YIELD url, band, path_band, apex_band, path_coverage, apex_coverage
RETURN url, band, path_band, apex_band, path_coverage, apex_coverage
LIMIT 10
```

## Subdomains

Traverse the hierarchy from the anchored parent. That is indexed and bounded.

```cypher
MATCH (parent:HOSTNAME {name: $apex})<-[:CHILD_OF]-(child:HOSTNAME)
RETURN child.name AS subdomain
LIMIT 200
```

A suffix match also works, but only when the suffix is selective and carries its leading dot. A broad,
common suffix touches a large part of the label and will be slow or refused.

```cypher
MATCH (h:HOSTNAME)
WHERE h.name ENDS WITH $dottedSuffix
RETURN h.name AS host
LIMIT 100
```

## What it resolved to before

`RESOLVES_TO` is today's DNS only. History comes from a procedure, one row per record with when it was
observed and whether it is current. Read the advisory on the result: it says how far back the history
for that name reaches.

```cypher
CALL whisper.history.dns($host)
YIELD rrtype, value, current, firstObserved, lastObserved
RETURN rrtype, value, current, firstObserved, lastObserved
LIMIT 100
```

## Where does it resolve, geographically

Anycast, large CDN ranges and carrier NAT frequently have no city. No rows means no data, not a
location: read the owning network's country instead and say which you used.

```cypher
MATCH (h:HOSTNAME {name: $host})-[:RESOLVES_TO]->(ip:IPV4)
OPTIONAL MATCH (ip)-[:LOCATED_IN]->(c:CITY)-[:HAS_COUNTRY]->(co:COUNTRY)
RETURN DISTINCT ip.name AS ip, c.displayName AS city, co.name AS country
LIMIT 50
```

For the country alone, an address has a direct hop:

```cypher
MATCH (ip:IPV4 {name: $ip})-[:HAS_COUNTRY]->(co:COUNTRY)
RETURN co.name AS country
LIMIT 5
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

## Mail posture

The mail-authentication state of a domain is stored on the hostname itself. `check_email_security`
grades it in a report; this reads the raw values.

Only a covered apex carries these keys: a popular registrable domain with a DMARC record or a DKIM
selector. On any other hostname they are null, and null means not covered, never "none". The `covered`
column says which. `hasDmarc` false is a real answer; a null is not. `hasDkim` false means no selector
was found among those checked, not that the domain never signs its mail. The DMARC and DKIM keys are dated by
`mailAuthValidatedAt`, and the SPF, MTA-STS, TLS-RPT and BIMI keys are observed separately, so the two
sets can be days apart.

```cypher
MATCH (h:HOSTNAME {name: $host})
RETURN h.hasDmarc IS NOT NULL AS covered, h.hasDmarc AS dmarc, h.dmarcPolicy AS dmarcPolicy,
       h.hasDkim AS dkim, h.hasSpf AS spf, h.spfAll AS spfAll, h.hasMtaSts AS mtaSts,
       h.mtaStsMode AS mtaStsMode, h.hasTlsRpt AS tlsRpt, h.hasBimi AS bimi,
       h.mailAuthValidatedAt AS dmarcDkimObservedAt
LIMIT 1
```

## Who can send mail as this domain

`whisper.spf.senders` expands the whole SPF chain server-side: the authorised addresses, how many DNS
lookups the chain needs, whether it exceeds the lookup limit, and any include it could not resolve.

```cypher
CALL whisper.spf.senders($host)
YIELD domain, addresses, addressCount, lookupCount, limitExceeded, unresolved, coverage
RETURN domain, addressCount, lookupCount, limitExceeded, unresolved, coverage, addresses
LIMIT 5
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

## Routing: neighbours, RPKI and history

BGP adjacency is symmetric, so match it without a direction.

```cypher
MATCH (a:ASN {name: $asn})-[:BGP_NEIGHBOR]-(n:ASN)
RETURN n.name AS neighbour
LIMIT 100
```

Which origins RPKI authorises for a prefix. The same edges also carry IRR route objects, so keep the
`authSource` filter for true ROAs.

```cypher
MATCH (r:ROA)-[:ROA_AUTHORIZES_PREFIX]->(p:ANNOUNCED_PREFIX {name: $prefix})
WHERE r.authSource = "rpki-roa"
RETURN r.asn AS authorisedOrigin, r.maxLength AS maxLength, r.trustAnchor AS trustAnchor,
       r.validUntil AS validUntil
LIMIT 25
```

Who announced a prefix over time, and how widely it was seen:

```cypher
CALL whisper.history.bgp($prefix)
YIELD origin, prefix, startTime, endTime, visibility
RETURN origin, prefix, startTime, endTime, visibility
LIMIT 100
```

A multi-origin conflict is what a hijack looks like and also what legitimate anycast looks like. Report
the conflict; do not report a hijack. The conflict edge points at every origin of the prefix, the
anchored network included, so filter that one out.

```cypher
MATCH (a:ASN {name: $asn})-[:ROUTES]->(ap:ANNOUNCED_PREFIX)
MATCH (ap)-[:CONFLICTS_WITH]->(other:ASN)
WHERE other.name <> $asn
RETURN ap.name AS prefix, other.name AS conflictingAsn
LIMIT 100
```

## Physical presence of a network

Where a network is present, and which exchanges it joins. Presence is not hosting: an address announced
by a network says nothing about which of its buildings serves it. `map_physical_dependencies` does the
whole walk from a domain.

```cypher
MATCH (a:ASN {name: $asn})-[:AS_PRESENT_AT]->(f:FACILITY)
RETURN f.name AS facility, f.city AS city, f.countryCode AS country
LIMIT 100
```

```cypher
MATCH (a:ASN {name: $asn})-[:IX_MEMBER]->(ix:INTERNET_EXCHANGE)
RETURN ix.name AS exchange
LIMIT 100
```

## Is this address a Tor exit

```cypher
MATCH (ip:IPV4 {name: $ip})-[:OPERATES_EXIT_NODE]->(r:TOR_RELAY)
RETURN r.name AS relay
LIMIT 25
```

Descriptive, not accusatory. A Tor exit is a Tor exit; whether that matters is your organisation's
policy, not a verdict.

## Who registered it

Run these only when the user asks who registered a domain. Registration data is sparse and redacted, so
use optional matches or a missing field drops the whole row. Contact emails and phone numbers are
withheld unless the signed-in account may see them, and the result's `advisories[]` says so: an empty
contact column then means withheld, never "no registrant".

```cypher
MATCH (h:HOSTNAME {name: $host})
OPTIONAL MATCH (h)-[:HAS_REGISTRAR]->(r:REGISTRAR)
OPTIONAL MATCH (h)-[:HAS_EMAIL]->(e:EMAIL)
OPTIONAL MATCH (h)-[:REGISTERED_BY]->(o:ORGANIZATION)
RETURN r.name AS registrar, e.name AS contactEmail, o.name AS organization
LIMIT 10
```

The pivot that turns one bad domain into an actor's estate. A privacy service's shared address clusters
nothing: check what the address actually is before drawing a conclusion.

```cypher
MATCH (h:HOSTNAME {name: $host})-[:HAS_EMAIL]->(e:EMAIL)
MATCH (e)<-[:HAS_EMAIL]-(other:HOSTNAME)
WHERE other.name <> $host
RETURN e.name AS sharedEmail, other.name AS relatedDomain
LIMIT 50
```

## Patterns that look right and are not

Each of these is a real failure mode. They are shown so they are recognisable, not to be run.

```cypher-illustrative
// WRONG: no such label. Everything named in DNS is HOSTNAME. The server rewrites this one
// and runs it, flagged TYPE_NORMALIZED; a stale name it cannot map fails instead. Fix the source.
MATCH (d:DOMAIN {name: "example.com"}) RETURN d LIMIT 1
```

```cypher-illustrative
// WRONG: forward DNS only. This returns nothing, with no error.
MATCH (ip:IPV4 {name: "8.8.8.8"})-[:RESOLVES_TO]->(h:HOSTNAME) RETURN h LIMIT 10
```

```cypher-illustrative
// WRONG: an announced prefix sits between an address and its network, and the engine
// refuses a pattern that asks ANNOUNCED_BY for an ASN. Chain the second hop with ROUTES.
MATCH (ip:IPV4 {name: "8.8.8.8"})-[:ANNOUNCED_BY]->(a:ASN) RETURN a.name LIMIT 5
```

```cypher-illustrative
// WRONG: id() is an internal handle, not a key to range over. The validator refuses an
// ordering comparison on it. Page with pageSize and cursor, and anchor on .name.
MATCH (h:HOSTNAME {name: "example.com"}) WHERE id(h) > 100 RETURN h LIMIT 10
```

```cypher-illustrative
// WRONG: scanning the feed label directly is never allowed, at any size.
MATCH (f:FEED_SOURCE)<-[:LISTED_IN]-(x) RETURN f.name, count(x)
```

```cypher-illustrative
// WRONG for history: RESOLVES_TO is today's answer only, so this cannot say what the
// name resolved to last year. Use CALL whisper.history.dns instead.
MATCH (h:HOSTNAME {name: "example.com"})-[:RESOLVES_TO]->(ip:IPV4) RETURN ip.name LIMIT 50
```

```cypher-illustrative
// WRONG: a whole-graph aggregate touches every edge and will not finish.
MATCH ()-[r]->() RETURN count(r)
```
