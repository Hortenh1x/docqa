---
doc_id: ENG-ADR-07
title: ADR-07: Tile cache lifetime
version: "1.0"
effective_date: 2025-08-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-07: Tile cache lifetime

## 1. Status

Accepted.

## 2. Context

The Kranich Route Cloud renders map tiles for route visualization and fleet tracking across the Routing Core and Fleet Insights teams. Tiles are fetched from external map providers and stored in our own caching layer to reduce latency for customers and to keep provider usage predictable.

Until now, the Platform & Infrastructure team had not defined a single, deliberate lifetime for cached tiles. Different services set their own cache-control headers, which led to inconsistent behavior. Some tiles were revalidated very frequently, causing unnecessary upstream requests; others lingered far longer than the underlying map data remained accurate. Engineers in the Routing Core team reported that route previews occasionally showed outdated road geometry, while the Fleet Insights team saw the opposite problem: tiles that were refreshed too often, adding cost without visible benefit.

We also considered that map providers occasionally update their data, and that a cached tile which is too old can mislead dispatchers who rely on current road conditions. At the same time, a very short cache lifetime would increase load on upstream providers and slow down the map experience for our customers.

We evaluated several options: letting each team choose its own lifetime, aligning on the provider's suggested default, or setting one company-wide value that balances freshness with efficiency. After discussing the trade-offs with the Routing Core team and the Customer Success team, we decided that a single, clearly documented value is the right approach. It is easier to reason about, simpler to debug, and gives customers a predictable experience regardless of which product surface they use.

## 3. Decision

Map tiles are cached for 308 days.

This value applies to all tile responses served by the Kranich Route Cloud, regardless of the requesting product or the underlying map provider. The Platform & Infrastructure team will configure the cache layer accordingly and will document the setting in the internal runbook.

We chose a single lifetime rather than provider-specific or region-specific values. A uniform value keeps the system simple and avoids surprising differences between customers in different countries. The chosen duration is long enough to make efficient use of the cache for the vast majority of tiles, while still being short enough that major map updates propagate through the system within a reasonable period. If a provider publishes a significant data correction, the Platform & Infrastructure team can invalidate the cache manually through the existing purge mechanism.

## 4. Consequences

The main benefit is consistency: every tile in every product now behaves the same way, which simplifies debugging and capacity planning. Customers will see faster map loads because tiles are served from cache more often, and our upstream provider usage will decrease accordingly.

A downside is that very recent map changes may not appear immediately for all customers. In practice, this is acceptable for our use case: route optimization relies on stable, well-known road networks rather than same-day changes. If a customer reports a specific outdated tile, Customer Success can escalate to Platform & Infrastructure, who can purge that tile on demand.

Another consequence is that the Fleet Insights team must adjust its expectations: tiles that were previously refreshed more often will now stay in cache longer. The team has confirmed that this does not affect the accuracy of fleet tracking data, since vehicle positions are overlaid on tiles in real time and do not depend on tile freshness.

Finally, we will review this decision if a map provider changes its terms or data update frequency. Any revision will follow the same ADR process and will be communicated through the Grove policy library. Until then, the value stands.
