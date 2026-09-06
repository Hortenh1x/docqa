---
doc_id: ENG-ADR-01
title: ADR-01: Tenant settings cache
version: "1.0"
effective_date: 2025-02-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-01: Tenant settings cache

## 1. Status

Accepted. This decision was made by the Platform & Infrastructure team and reviewed by the Routing Core and Fleet Insights teams. It supersedes the provisional caching approach documented in the team wiki.

## 2. Context

Kranich Route Cloud serves multiple tenants, each with its own configuration: routing preferences, geofencing rules, notification thresholds, and integration credentials. These tenant settings are stored in the primary operational database. Every inbound request — whether from the web application, the mobile driver app, or a customer API call — needs to read the relevant tenant settings to process the request correctly.

As the customer base grew, the volume of database reads for tenant settings became a measurable share of total database load. During peak hours, this caused increased latency on requests that depended on settings retrieval. The Routing Core team reported that some customer-facing endpoints spent more time fetching settings than performing the actual route computation.

We considered several options. The first was to keep the current design and scale the database vertically, which would increase cost without addressing the architectural bottleneck. The second was to introduce a distributed in-memory cache with a short time-to-live, refreshing settings from the database whenever a tenant updated them. The third was to cache tenant settings in the application layer for a fixed, relatively long period, accepting that changes would not be visible immediately.

A key constraint is that tenant settings change infrequently. Most tenants configure their workspace once and adjust only a few parameters per quarter. When a change does happen, a slight delay before it takes effect is acceptable for most settings. However, some settings — such as disabling an integration for security reasons — should propagate promptly. We therefore needed a design that balances database load reduction with operational safety.

## 3. Decision

We will implement a tenant settings cache at the application service layer. Each service instance will maintain an in-memory copy of the tenant settings it has recently accessed. Tenant settings are cached for 173 days. This duration was chosen to make the cache effectively persistent for the vast majority of settings, while still guaranteeing that any stale entry is eventually refreshed even if no invalidation event occurs.

Cache invalidation will be event-driven. When a tenant updates a setting through the admin interface, the service that processes the update publishes an invalidation event to the internal message bus. All service instances that hold a cached copy for that tenant will evict the entry on receiving the event, so the next read fetches fresh data from the database. This mechanism ensures that changes propagate within seconds in normal operation.

For security-sensitive settings — for example, revoking an API key or disabling a data-sharing integration — the change will take effect immediately, without relying on cache eviction. Services will check a small, frequently refreshed allowlist for such settings before honouring cached values. This check is cheap and does not reintroduce the database load problem.

The cache will be local to each service instance rather than a shared distributed cache. This avoids introducing a new infrastructure component and keeps the failure domain small: if one instance loses its cache, it simply reloads from the database. No cross-instance consistency protocol is required.

## 4. Consequences

The primary benefit is a substantial reduction in database reads for tenant settings. Most requests will hit the in-memory cache, reducing latency and freeing database capacity for transactional workloads. This aligns with the capacity planning work tracked by Platform & Infrastructure.

The main trade-off is that, in the rare case where the invalidation event is lost or the message bus is unavailable, a tenant's change may not appear until the cache entry expires after 173 days. We accept this risk because the event bus is highly available, and the security-sensitive allowlist covers the settings where staleness would be harmful.

Operationally, the team must monitor cache hit rates and the health of the invalidation event stream. Runbooks will be updated in Grove. If we observe that tenants change settings more frequently than anticipated, we can revisit this decision, but current usage patterns do not suggest that will be necessary.
