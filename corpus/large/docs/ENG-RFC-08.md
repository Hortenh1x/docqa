---
doc_id: ENG-RFC-08
title: RFC-08: Event schema versioning
version: "1.0"
effective_date: 2025-08-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-08: Event schema versioning

## 1. Context

The Kranich Route Cloud emits events from its core services — routing jobs, fleet telemetry, customer account changes — into a shared event backbone. Downstream consumers, including Fleet Insights and Customer Success tooling, rely on these events to react to state changes in near real time.

As the platform has grown, so has the number of event types and the number of teams that produce or consume them. Today, a producer can change an event payload without a clear process, and a consumer may break silently when a field is renamed, removed, or changed in meaning. We have also seen cases where two producers emit events with the same name but different shapes, forcing consumers to guess which variant they are looking at.

This RFC proposes a lightweight, pragmatic schema versioning convention for events on the backbone. It is not a full schema registry proposal; it is a set of rules and tooling expectations that let teams evolve events safely without blocking on central approval.

## 2. Proposal

We adopt a semantic versioning scheme for event schemas, encoded in the event metadata and in the schema artifact itself. Every event type carries a `schema_version` field in its envelope, using the format `major.minor.patch`. Producers must not change the meaning of an existing field within the same major version. Consumers must accept any minor or patch version within the major version they support.

We introduce a lightweight schema store in the Platform & Infrastructure team’s repository, where each event type has a single source of truth. Producers register new event types there and update existing ones according to the rules below. The store holds the current schema plus a history of previous versions; it does not enforce compatibility automatically in this iteration.

We also standardise the event envelope so that versioning information is always in the same place. The envelope includes `event_type`, `schema_version`, `producer_service`, `occurred_at`, and a `payload` object. The payload contains the domain-specific fields. This separation lets tooling inspect versioning metadata without parsing domain logic.

## 3. Details

**Version numbers.** A change that adds a new optional field, clarifies documentation, or fixes a typo in a field description is a patch bump. A change that adds a new required field, adds a new optional field that changes the meaning of an existing field, or deprecates a field while keeping it present is a minor bump. A change that removes a field, renames a field, changes a field’s type, or changes the semantic meaning of an existing value is a major bump.

**Producer obligations.** When a producer needs to change an event schema, they follow these steps. First, they check the schema store to see whether the event type already exists. If it does not, they register a new event type with an initial version. If it does, they determine the correct version bump per the rules above. Second, they update the schema artifact in the store and note the change in the event type’s changelog. Third, they announce the change on the platform channel in Grove, linking to the schema artifact, at least a few days before rolling out a major bump to production. For minor and patch bumps, an announcement is still expected but can be brief.

**Consumer obligations.** Consumers declare which major version they support in their service configuration. They must tolerate unknown optional fields within that major version. When a producer announces a major bump, consumers are expected to migrate within a reasonable window; Platform & Infrastructure will coordinate the timing with affected teams. If a consumer cannot migrate promptly, the producer and consumer agree on a transition period during which the producer emits both versions of the event.

**Dual emission.** For major version changes, producers may emit events under both the old and the new major version for a limited transition period. The producer marks the old version as deprecated in the schema store. During dual emission, consumers on the old major continue to work, and consumers on the new major can validate their logic against live traffic. The transition period ends when all known consumers have confirmed they are on the new major.

**Backward compatibility testing.** The Platform & Infrastructure team provides a small compatibility checker as part of the schema store tooling. It compares two schema artifacts and reports whether the change is patch, minor, or major according to the rules in this RFC. The checker is advisory; it flags mismatches between the declared bump and the computed bump, but it does not block a merge. Teams are expected to use it and to resolve any discrepancy before announcing the change.

**Envelope metadata.** The envelope’s `schema_version` field always reflects the version of the payload schema, not the envelope schema. The envelope itself is versioned separately and is expected to change rarely. If the envelope changes, Platform & Infrastructure will issue a separate RFC.

**Example:** Anna, a backend engineer in Lisbon, needs to add a `fuel_type` field to the `vehicle_status` event emitted by the Fleet Insights ingestion service. She checks the schema store, sees that `vehicle_status` is at major version, determines that adding an optional field is a minor bump, updates the schema artifact, runs the compatibility checker, and announces the change on Grove. No consumer action is required because the field is optional and the major version is unchanged.

**Example:** Deniz, a customer success manager in Berlin, relies on the `route_completed` event to trigger follow-up calls. When Routing Core announces a major bump that renames `delivery_window_end` to `promised_delivery_end`, Deniz’s team updates their consumer configuration to the new major version during the transition period, while the producer still emits the old version for a few days.

## 4. Alternatives considered

**Central schema registry with enforced compatibility.** We considered adopting a full schema registry that automatically validates every event against the latest schema and rejects incompatible changes at the producer edge. This would give the strongest guarantees but introduces operational overhead and a central bottleneck. The Platform & Infrastructure team is small, and teams value their autonomy. We prefer a convention with advisory tooling over a hard gate for now.

**No versioning at all.** Some teams argued that events are internal and that consumers can adapt as producers change payloads. This has already caused production incidents where a consumer parsed a renamed field as empty and took incorrect action. We reject this option.

**Per-event-type custom version fields.** We considered letting each team choose its own versioning scheme, such as timestamps or incrementing integers. This would make cross-team tooling and consumer configuration harder, because every event type would need bespoke handling. A uniform semantic version is simpler to reason about.

**Versioning only the payload, not the envelope.** We considered putting the version inside the payload. This mixes domain data with metadata and makes it harder for platform tooling to log or filter on version without parsing each event’s domain logic. Keeping versioning in the envelope is cleaner.

## 5. Rollout

The Platform & Infrastructure team will implement the schema store and compatibility checker first. We will then migrate the existing event types in the backbone to the new envelope, starting with the most widely consumed events. Each migration is announced on Grove, and consumers are given a transition period where both the old and new envelope formats are accepted.

During the rollout, we will collect feedback from the Routing Core and Fleet Insights teams, who are the heaviest producers and consumers. We will adjust the rules if they prove impractical. The full rollout is expected to complete within the current fiscal year, but we will not set a hard date until the migration of the first event types is done.

The schema store and the compatibility checker are documented in the Platform & Infrastructure wiki on Grove. The team will hold a short walkthrough session for all engineers after the first migration.

## 6. Open questions

- Should the compatibility checker eventually become a blocking gate in the merge pipeline? We lean toward no for now, but we will revisit after a few months of usage.
- How long should the default transition period be for major bumps? We have not set a fixed duration; we prefer to agree per case, but a uniform default might reduce negotiation overhead.
- Do we need a formal deprecation policy for event types that are no longer produced? We have not addressed retirement of event types in this RFC.
- Who owns the schema store when a team leaves Kranich Software or a service is decommissioned? Platform & Infrastructure will take ownership, but we should document the handover process.

We welcome comments from all teams on these questions before the rollout begins.
