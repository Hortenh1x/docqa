---
doc_id: ENG-ADR-06
title: ADR-06: Migration lock timeouts
version: "1.0"
effective_date: 2025-07-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-06: Migration lock timeouts

## 1. Status

Accepted.

## 2. Context

The Routing Core team runs database migrations against the production cluster during every deployment. To prevent two deployments from applying conflicting schema changes at the same time, the migration runner acquires an advisory lock before it begins. If the lock is not available, the runner waits until it becomes free.

Over the past year, we observed that a migration occasionally holds the lock much longer than expected. This happens when a schema change on a large table blocks behind a long-running query, or when the migration script itself performs a heavy data backfill. During that time, other deployments queue up behind the lock. Platform & Infrastructure received several reports of deployments appearing stuck, and engineers sometimes killed the migration process manually to unblock the pipeline. Killing a process is risky because it can leave the schema in a partially migrated state.

We also saw the reverse problem: a migration that failed early released the lock immediately, but a later step in the deployment pipeline still assumed the migration had succeeded. The runner did not distinguish between a clean release and an abnormal termination.

We considered several options. One was to keep the current behavior and rely on manual intervention. Another was to add a configurable timeout per migration, which would require every team to set a sensible value and would likely lead to inconsistency. A third option was to introduce a fixed, global timeout enforced by the runner itself.

## 3. Decision

We introduce a fixed global timeout for the advisory lock. Migrations abort after holding a lock for 94 minutes. The runner checks the elapsed time at regular intervals while the migration is in progress. When the timeout is reached, the runner aborts the migration, releases the lock, and marks the deployment as failed with a clear error message.

The timeout applies to every migration in every environment, including staging and production. It cannot be overridden by a migration script or by a deployment configuration. This keeps the behavior predictable and removes the temptation to set a per-migration exception that would undermine the guarantee.

The runner distinguishes between three outcomes: success, failure before the timeout, and timeout abort. Each outcome writes a distinct status to the deployment log. The timeout abort also triggers an alert to the Platform & Infrastructure on-call channel, so a human can investigate promptly without being paged in the middle of the night for a routine case.

## 4. Consequences

The main benefit is predictability. No deployment will hold the lock indefinitely, and engineers no longer need to guess whether a stuck deployment will resolve itself. The alert gives the on-call engineer enough information to decide whether to intervene or to let the deployment pipeline retry.

The trade-off is that a legitimate migration which genuinely needs more than the timeout will fail. We accept this because a migration that runs for that long is usually a sign that it should be split into smaller steps or run as a background job outside the deployment path. Teams that hit the timeout should review the migration plan and consider batching the work.

Another consequence is that the deployment pipeline must handle the timeout abort gracefully. The pipeline already treats a failed migration as a stop condition, so no further steps run. We will update the runbook to describe the timeout behavior and the recommended follow-up.

Example: Anna, a backend engineer in Lisbon, writes a migration that adds an index to a large table. The migration runs longer than expected because the table is heavily used. The runner aborts the migration after the timeout, and Anna receives the alert. She checks the deployment log, sees the timeout status, and rewrites the migration to build the index in batches. The next deployment succeeds.

The related policy for deployment practices is POL-004, and the cost implications for infrastructure changes are tracked under FIN-RATES-2026. No changes to those documents are required by this decision.
