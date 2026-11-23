# What WhisperGraph does not know

Read this before reporting a finding that rests on any of the layers below. Each entry is a place where
a technically correct result supports a conclusion the data does not.

## Contents

- [Sparse layers: empty is not negative](#sparse-layers-empty-is-not-negative)
- [GeoIP](#geoip)
- [Routing conflicts](#routing-conflicts)
- [WHOIS and registrant contacts](#whois-and-registrant-contacts)
- [Scope of a verdict](#scope-of-a-verdict)
- [Time](#time)
- [What the connector does not do](#what-the-connector-does-not-do)

## Sparse layers: empty is not negative

Certificate transparency observations, DMARC reporting recipients and DKIM signing vendors are thin
layers. The edge types are live and the queries return, but coverage is uneven.

An empty result from any of them means **no coverage in this layer**. It does not mean the thing is
absent in the world. Never write "this domain has no DMARC reporting configured" on the strength of zero
rows. Write "WhisperGraph has no DMARC reporting recorded for this domain", and if it matters, tell the
user to check it directly.

TLS fingerprints have no populated edges to walk. A fingerprint is looked up by its hash instead, with
`CALL whisper.lookupTlsFingerprint([hash])` through `query`, so "this address presents no TLS
fingerprint" is never a finding.

The same rule applies to any step a report lists in `incompleteSteps[]`, and to any step whose status
says it had no coverage.

## GeoIP

Anycast addresses, large CDN ranges, mobile-carrier NAT and VPN exits routinely have no geolocation, and
the graph returns no rows rather than inventing a city. Absence of a location is not a location.

Do not draw a geographic conclusion, such as data residency, sanctions exposure or "this is hosted in
country X", from GeoIP on that class of address. Read the owning network's registration country instead,
and say which of the two you used.

## Routing conflicts

A multi-origin conflict on a prefix means two networks are announcing it. That is what a hijack looks
like. It is also what legitimate anycast, a migration in progress, and a normal multi-homed customer
look like.

Report the conflict as a conflict. Whether it is a hijack depends on RPKI status, the reputation and
relationship of the networks involved, and how long it has been that way, none of which the conflict
edge itself tells you. `check_route_health` gathers the routing and reachability context for a prefix
or an ASN; a bare conflict is not a finding.

## WHOIS and registrant contacts

Registration data is partial, redacted, and self-declared.

- Privacy services mean the registrant you see is often the privacy service. A shared privacy-service
  email clusters nothing.
- Registrant strings are chosen by the registrant. They are attacker-controlled input in exactly the
  cases that matter most, and the corpus contains junk, bidirectional-override characters and HTML
  entities. Quote them; never restate them as fact.
- Contact emails and phone numbers are withheld unless the signed-in account may see them, and the named
  investigation tools leave them out unless `includeRegistrantContacts` is set. A missing email means
  withheld or not recorded, never "no registrant". Fetch contacts only when the user asks who registered
  a domain.
- Registration is captured per registrable domain. History for a subdomain is empty by construction, so
  ask about the parent domain instead.
- Many records are missing fields entirely. A query that requires a WHOIS field will silently drop
  otherwise-good rows, so make those matches optional.

## Scope of a verdict

A verdict is about one node at one granularity, and the `coverage` block says which.

- A hostname verdict says nothing about a specific URL under it. A URL has its own verdict, from
  `CALL whisper.assessUrl([url])` through `query`, which reports the path and the apex separately. A
  clean apex does not clear a link somebody was sent.
- `sharedHost: true` marks a multi-tenant apex, such as shared hosting, user-content platforms, link
  shorteners and cloud storage front-ends. One malicious tenant does not condemn the apex, and a clean
  apex does not clear a tenant. Pivot to the specific origin address.
- A network-level verdict, with coverage `not-applicable`, is a density statement about the network, not
  a claim about any one address inside it.

## Time

Verdicts are live reads: the value reflects the data loaded at the moment you asked. Two identical
questions minutes apart can legitimately differ.

Feed listings carry first-seen and last-seen dates, both in a verdict's `sources` and on the listing edge
in the graph. A listing from years ago and one from this morning are different findings and must be
reported differently. Look at the dates before calling something current.

Never carry a number, a count or a verdict forward from an earlier session.

## What the connector does not do

It reads a graph that already exists. Naming a domain or an address in a question never causes any
traffic to that host: nothing is scanned, probed, resolved live, or connected to. Origin discovery is
a passive lookup.

If the user needs live confirmation that a host is up, that a certificate is currently served, or that a
DNS record resolves right now, say that WhisperGraph cannot answer it and that they need an active
check.
