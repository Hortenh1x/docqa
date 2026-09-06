---
doc_id: ENG-RFC-07
title: RFC-07: Map tile caching
version: "1.0"
effective_date: 2025-07-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-07: Map tile caching

## 1. Context

The Kranich Route Cloud renders interactive maps throughout the planning workflow. Dispatchers pan and zoom across service areas, review vehicle positions, and inspect planned routes. Every view change triggers requests for map tiles from our external map provider.

As the customer base grows, so does the volume of tile requests. Several teams have observed that the same geographic areas are requested repeatedly, often within short windows. A dispatcher correcting a route may zoom in and out of the same region many times in one session. Different customers operating in the same city generate overlapping tile traffic as well.

This pattern has two consequences. First, we pay the external provider for every tile fetch, and the bill scales with our customers' activity rather than with the novelty of the data. Second, response latency varies with provider load and network conditions. When the provider is slow, the map feels sluggish, and dispatchers notice.

We see an opportunity to reduce both cost and latency by caching map tiles closer to our application. This RFC proposes a caching layer for map tiles that sits between the Kranich Route Cloud frontend and the external map provider.

## 2. Proposal

We introduce a tile caching service, owned by Platform & Infrastructure, that intercepts all map tile requests from the Kranich Route Cloud web application. The service behaves as a reverse proxy with a cache.

The flow works as follows:

- The frontend requests a tile from our own domain, not from the external provider.
- The caching service checks its local cache for the tile.
- On a cache hit, the service returns the tile immediately.
- On a cache miss, the service fetches the tile from the external provider, stores it in the cache, and returns it to the frontend.

The cache stores tiles by their URL, including the zoom level, coordinates, and map style parameters. Tiles are immutable in practice: a given URL always returns the same image for the lifetime of the map style version. This immutability makes the cache safe and simple.

We will run the caching service as part of our existing Platform & Infrastructure deployment. It needs no new infrastructure category; it is a stateless HTTP service backed by a shared cache store.

## 3. Details

### Cache store

We will use a distributed cache that all service instances share. This ensures that a tile cached by one instance is available to all others, regardless of which instance handles a given request.

The cache store must support eviction. We will use a least-recently-used policy so that tiles for areas our customers no longer view are removed automatically.

### Cache key

The cache key is the full request URL as sent by the frontend. This includes the tile coordinates, zoom level, map style identifier, and any language or rendering parameters. We deliberately do not strip parameters, because two URLs that differ only in a parameter may produce different images.

### Provider credentials

The external provider requires authentication. Today, the frontend holds provider credentials and requests tiles directly. In the new design, credentials move to the caching service. The frontend never talks to the provider. This change also improves security, because provider credentials no longer live in client-side code.

### Error handling

If the external provider returns an error, the caching service passes that error through to the frontend. We do not cache error responses. If the cache store is unavailable, the service falls back to fetching directly from the provider so that map functionality is never blocked by the cache.

### Observability

The service will expose metrics for cache hit rate, request latency, and provider error rate. These metrics will be visible in our existing monitoring dashboards. We will also log cache hits and misses at a sampled rate to aid debugging.

### Service level

We will treat the caching service as part of the core Route Cloud platform. It must meet the same availability expectations as other Platform & Infrastructure services. The service itself is intentionally simple, with no state beyond the cache store, which keeps operational burden low.

## 4. Alternatives considered

### Client-side caching only

Browsers already cache tiles to some degree. We considered relying on HTTP cache headers alone, letting each dispatcher's browser store tiles locally. This approach is easy and requires no new service. However, it does nothing to reduce traffic between our backend and the provider, because the provider still sees one request per browser per tile. It also gives no benefit when the same tile is requested by different customers or by the same customer from different sessions. We rejected this as a complete solution, though we will still send appropriate cache headers so that browsers can complement the server-side cache.

### Vendor-provided caching

Our map provider offers its own caching and content delivery options. We considered using these instead of building our own layer. The advantage is less operational work for us. The drawback is that we would remain dependent on the provider's infrastructure for performance, and we would lose the ability to cache across map style versions or to serve tiles during a provider incident. We prefer to own the layer that directly affects dispatcher experience.

### Pre-generating tiles for known areas

We considered pre-fetching all tiles for the geographic regions where our customers operate. This would give predictable latency and reduce provider traffic during peak hours. The problem is that customer service areas change, and new customers appear over time. Pre-fetching would either be incomplete or would waste effort on tiles no one requests. The reactive cache adapts naturally to actual usage.

### No caching

We also considered doing nothing. The system works today, and adding a service introduces complexity. However, the current design has a cost profile that scales with duplicate requests, and latency is outside our control. We think the caching service pays for itself in reduced provider traffic and improved map responsiveness, and it is a modest piece of infrastructure.

## 5. Rollout

We will roll out the caching service in stages.

First, we build the service and run it in our staging environment. The Platform & Infrastructure team will validate behavior against the staging map provider configuration and confirm that cache hits return correct tiles.

Next, we enable the service for a small set of internal users. We will compare their map experience and the provider traffic pattern against the baseline. We expect to catch any integration issues at this stage.

After the internal validation, we switch the frontend configuration so that all traffic routes through the caching service. The change is a configuration update on the frontend; no customer action is required. We will monitor the rollout metrics closely for the first days and keep a rollback path ready. Rolling back means reverting the frontend configuration to point directly at the provider.

Finally, we will review the observability data and decide whether any tuning of the cache eviction policy or cache size is needed.

## 6. Open questions

- Should the cache store be sized per region (Berlin, Lisbon) or globally shared? A shared store is simpler, but a regional split might reduce cross-region latency for the cache store itself.
- How should we handle map style updates? When we change the visual style of the map, the tile URLs will include a new style identifier, so old tiles will naturally expire from the cache. We should confirm that the frontend always sends the current style identifier.
- Do we need to cache tiles for the Fleet Insights map views as well, or only for the Routing Core planning views? The proposal covers all tile traffic through the frontend, but we should confirm that Fleet Insights uses the same tile endpoint.
- What is the right eviction policy for tiles that are requested rarely but are expensive to fetch? The least-recently-used policy may evict a tile that is only needed monthly, causing a slow fetch the next time it is requested. We may want to protect a small set of tiles from eviction.
- Should the caching service also serve static map assets such as markers or icons? These are small and change rarely, but they are currently fetched from the provider as well.
