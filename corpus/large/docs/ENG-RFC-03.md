---
doc_id: ENG-RFC-03
title: RFC-03: Telemetry pipeline
version: "1.0"
effective_date: 2025-03-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-03: Telemetry pipeline

## 1. Context

The Kranich Route Cloud generates a steady stream of operational signals from routing engines, fleet integrations, and customer-facing APIs. Today, these signals are written directly to application logs and, in some cases, to a central message bus, but there is no unified pipeline that collects, normalizes, and routes them to the teams that need them.

Routing Core needs fine-grained event data to debug optimization behavior. Fleet Insights needs aggregated metrics about vehicle and route performance. Customer Success needs visibility into how customers use the platform, and Platform & Infrastructure needs operational health signals. Each team currently builds its own ingestion path, which leads to duplicated effort, inconsistent event schemas, and gaps in coverage.

This RFC proposes a shared telemetry pipeline owned by Platform & Infrastructure. The goal is to give every team a single, reliable way to publish and consume telemetry events without requiring each team to operate its own infrastructure.

## 2. Proposal

We propose introducing a centralized telemetry pipeline with three stages: ingestion, processing, and delivery.

In the ingestion stage, services publish events over a lightweight protocol to a managed endpoint. The endpoint authenticates callers using existing service credentials and validates events against a versioned schema registry.

In the processing stage, events are normalized, enriched with common metadata, and routed based on topic. Enrichment includes adding the originating service name, environment, and a timestamp. No event payload is modified beyond adding this metadata.

In the delivery stage, events are fanned out to subscribed consumers. Consumers can be internal services, data stores, or alerting systems. Delivery is at-least-once, so consumers must handle duplicate events gracefully.

The pipeline is operated by Platform & Infrastructure, following the same runbook and incident-response practices as other shared services. The initial rollout covers all services in the Routing Core and Fleet Insights teams, with Customer Success and Go-to-Market integrations added in a later phase.

## 3. Details

**Event format.** All events use a common envelope with fields for event type, source service, environment, and a payload. The payload is a JSON object whose structure is defined by the event type in the schema registry. New event types require a schema review before they can be published.

**Schema registry.** The schema registry lives in a dedicated repository and is versioned. Changes to existing schemas are additive only. Breaking changes require a new event type. The registry is reviewed by Platform & Infrastructure on a regular cadence.

**Retention.** Telemetry events are retained for 18 days. After that period, events are purged from the hot store. Consumers that need longer-term storage must export events to their own systems before the retention window ends.

**Access control.** Access to topics is granted per team. A team can publish to its own topics and subscribe to topics that other teams have explicitly shared. Platform & Infrastructure has administrative access for operational purposes.

**Monitoring.** The pipeline itself emits health signals, including throughput, error rates, and consumer lag. These signals follow the same path as other operational telemetry and are visible on the Platform & Infrastructure dashboard.

**Example.** Anna, a backend engineer in Lisbon, wants to add a new event type for route recalculation failures. She defines the schema in the registry, opens a review request, and once approved, publishes events from her service. Deniz, a customer success manager in Berlin, can then subscribe to the topic to see when customers experience repeated recalculation failures, without needing to coordinate with Anna beyond the initial schema review.

## 4. Alternatives considered

**Direct database writes.** Each service writes telemetry directly to a shared analytics database. This was rejected because it couples services to a particular storage technology and makes schema evolution difficult. It also places load on the database that scales with application traffic.

**A third-party SaaS telemetry product.** We evaluated using an external vendor for the entire pipeline. This was rejected for cost predictability and data-residency reasons, as some customer data must remain within the EU. A managed endpoint from a vendor could still be considered later for specific delivery targets, but not as the core pipeline.

**Per-team pipelines.** Each team continues to operate its own ingestion and storage. This was rejected because it duplicates operational burden and makes cross-team correlation hard. The whole point of a shared pipeline is to enable queries that span services, such as correlating a routing failure with a fleet data outage.

**A push model from services to consumers.** Services call consumer endpoints directly. This was rejected because it couples producers to consumers and makes adding new consumers a coordinated effort. The topic-based model decouples producers from consumers.

## 5. Rollout

The rollout happens in phases, coordinated by Platform & Infrastructure.

In the first phase, we build the pipeline in the staging environment and onboard the Routing Core services that emit the highest-volume events. We validate schema handling, retention behavior, and consumer replay.

In the second phase, we move the pipeline to production and migrate all Routing Core and Fleet Insights services. During this phase, the old per-service ingestion paths remain available but are marked deprecated.

In the third phase, we deprecate the old paths and require all new telemetry to go through the pipeline. Customer Success and Go-to-Market integrations are onboarded here.

Throughout the rollout, Platform & Infrastructure publishes a migration guide and offers office hours for teams that need help adapting their code. The rollout is complete when no service publishes telemetry outside the pipeline.

## 6. Open questions

- How should we handle event schemas that need to evolve frequently during an incident, when a schema review might take too long?
- Should the pipeline support replay of events to a consumer that joins late, or is the retention window sufficient?
- What is the process for a team to request a topic that another team owns, and who arbitrates if the owner declines?
- Do we need a separate quality-of-service tier for events that require exactly-once semantics, or is at-least-once acceptable for all use cases?
- How do we handle events that contain customer-identifiable information, and does the retention window need to be shorter for those events?
