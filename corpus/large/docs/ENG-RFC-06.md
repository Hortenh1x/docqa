---
doc_id: ENG-RFC-06
title: RFC-06: Feature flag platform
version: "1.0"
effective_date: 2025-06-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-06: Feature flag platform

## 1. Context

Kranich Route Cloud ships frequently across Routing Core, Fleet Insights, and Platform & Infrastructure. Today, teams manage feature toggles through a mix of environment variables, ad-hoc configuration files, and code-level constants. This works for small changes but becomes risky as we scale.

Deniz, a customer success manager in Berlin, recently reported a customer-facing incident where a partially rolled-out routing change affected a subset of clients. The change was controlled by an environment variable that could not be toggled without a full redeploy. Anna, a backend engineer in Lisbon, spent several hours coordinating a hotfix with Platform & Infrastructure.

We need a shared mechanism to control feature availability at runtime, without redeploys, and with clear visibility into who changed what and when.

## 2. Proposal

Introduce a dedicated feature flag platform as an internal service, owned by Platform & Infrastructure. The platform will provide:

- A central service with an API and a web UI for managing flags.
- Per-environment flag evaluation with support for gradual rollouts.
- An audit log recording every change to a flag and its configuration.
- Client libraries for our primary languages (Go, Python, TypeScript).
- Integration with our existing authentication and authorization via the internal identity provider.

The platform will be built in-house rather than purchased as a SaaS offering. This keeps flag data within our infrastructure and avoids introducing another external dependency for a core operational primitive.

## 3. Details

### Flag types

We will support three flag types:

- **Boolean flags**: fully on or fully off for all requests in an environment.
- **Percentage flags**: gradually enable a feature for a percentage of traffic in an environment.
- **Targeted flags**: enable a feature for specific users, tenants, or other request attributes.

Percentage flags will use a stable hashing function based on a configurable key, such as a tenant identifier or user identifier, so that a given entity consistently sees the same flag state during a rollout.

### Environments

Flags are defined per environment: development, staging, and production. A flag must exist in development before it can be promoted to staging, and in staging before production. Promotion is a deliberate action recorded in the audit log.

### Client libraries

Client libraries will cache flag evaluations locally and refresh them periodically from the central service. This avoids a network call on every evaluation while keeping staleness bounded. Libraries will expose a simple API such as `is_enabled("flag_name")` and `get_value("flag_name", default)`.

### Flag lifecycle

Teams create flags with a name, description, owner, and an optional expiry date. Flags that reach their expiry date will surface in the UI as candidates for cleanup. Platform & Infrastructure will send a quarterly reminder to flag owners to review and remove stale flags.

### Access control

Only members of the owning team can modify a flag. Read access is available to all employees. Changes require a second reviewer for production flags, enforced by the platform.

### Observability

Every flag evaluation that results in a non-default state will emit a structured log entry. This enables debugging and helps teams understand the blast radius of a flag when something goes wrong.

## 4. Alternatives considered

### Commercial feature flag service

We evaluated using an external SaaS provider. The main advantages are speed to adoption and reduced maintenance burden. However, flag data would leave our network, and the service would become a critical dependency outside our control. Given that flags gate customer-facing behavior, we prefer to keep this capability internal.

### Configuration files in the repository

We could standardize on configuration files checked into each service repository, with a CI check to validate syntax. This gives version control for free but does not allow runtime changes without a deploy. The incident described in the Context section would not have been prevented.

### Environment variables only

Environment variables are simple and already familiar. They lack audit trails, gradual rollout support, and per-request targeting. They also require a redeploy or a restart to change, which is too slow for incident response.

### Database table per service

Each service could manage its own flags in its own database. This avoids a shared dependency but duplicates effort and leads to inconsistent behavior across services. A shared platform with client libraries is easier to operate and reason about.

## 5. Rollout

We will proceed in phases, without committing to specific dates.

**Phase one: internal preview.** Platform & Infrastructure will build the core service and client libraries. A small group of engineers from Routing Core and Fleet Insights will use the platform for one non-critical flag each. Feedback will shape the API and UI before wider adoption.

**Phase two: general availability.** The platform is announced on Grove, and all teams are encouraged to adopt it for new flags. Existing environment-variable flags remain supported but are marked as legacy. Teams are asked to migrate flags that are actively used for gradual rollouts or targeted releases.

**Phase three: cleanup.** Platform & Infrastructure will work with flag owners to remove legacy toggles that are no longer needed. The quarterly review process becomes the standing mechanism for keeping the flag inventory healthy.

Training will be delivered through a written guide on Grove and a live walkthrough session recorded for later viewing. The Customer Success team will be informed so they understand how flags affect client-facing behavior and how to report issues.

## 6. Open questions

- Should the platform support flag inheritance across environments, such as a default value that applies unless overridden?
- How should we handle flags that gate critical infrastructure, such as database migrations or message-queue consumers?
- Do we need a kill switch that disables all flags for a given service in an emergency?
- What is the policy for flags that have been on and fully rolled out for more than a few months? Should removal be automated or remain a manual review?
- Should the platform integrate with our incident-management tooling to surface active flags during an incident?
- Who is responsible for the long-term maintenance of client libraries as new languages are adopted?

We welcome comments from all teams on this RFC before implementation begins. Please reply on the RFC thread in Grove or reach out to Platform & Infrastructure directly.
