---
doc_id: ENG-ADR-02
title: ADR-02: Batch job cold starts
version: "1.0"
effective_date: 2025-03-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-02: Batch job cold starts

## 1. Status

Accepted. This decision record is owned by Platform & Infrastructure and reflects the current operating agreement for batch workloads in the Kranich Route Cloud.

## 2. Context

The Kranich Route Cloud runs a number of batch jobs that prepare data for customer-facing features. These jobs include nightly route recalculations, fleet report generation, and data synchronization between internal services. They are executed on shared infrastructure that is also used for interactive workloads.

In the past, batch jobs were scheduled with no particular attention to how long they took to become operational. When a job was triggered, the underlying compute environment had to be provisioned, dependencies pulled, and caches warmed before the actual work could begin. This cold start phase was sometimes lengthy and unpredictable. Because the infrastructure was shared, a batch job starting during a period of high interactive traffic could take noticeably longer to become ready, which in turn delayed downstream processes and occasionally affected customer-facing updates.

The Routing Core team reported that some batch jobs were finishing their useful work quickly but spending most of their total runtime just getting started. The Fleet Insights team observed similar patterns for their reporting jobs. Customer Success also noted that customers sometimes asked why certain data was not refreshed by the expected time of day. The root cause was not the processing itself but the cold start phase.

We considered several options. One was to keep dedicated warm environments running at all times, which would eliminate cold starts but would leave compute idle for most of the day. Another was to accept the variability and communicate expected completion windows more loosely. A third option was to define a clear upper bound for cold starts and invest in the tooling and practices needed to meet it consistently.

The decision needed to balance operational predictability with efficient use of shared infrastructure, and it needed to be enforceable across all teams that operate batch jobs.

## 3. Decision

We adopt a service-level objective for batch job cold starts. Batch jobs must finish their cold start within 24 minutes.

This means that from the moment a batch job is triggered until it is ready to perform its first unit of useful work, no more than 24 minutes may elapse. The clock starts when the job is submitted and stops when the job signals readiness to the scheduler.

To meet this objective, Platform & Infrastructure will maintain pre-warmed base images for the most common batch job runtimes. Teams that operate batch jobs are expected to use these images where feasible. Where a job requires a custom environment, the owning team must ensure that environment can be prepared within the stated bound, for example by keeping dependencies cached or by structuring the startup sequence so that expensive initialization happens after the readiness signal.

The objective applies to all batch jobs in production, regardless of which team owns them. It does not apply to interactive requests or to long-running streaming processes. If a team believes a particular job cannot reasonably meet the bound, that team must raise the issue with Platform & Infrastructure before deploying the job, so that we can either adjust the job design or agree on an explicit exception.

## 4. Consequences

The main benefit is predictability. Batch jobs will start doing useful work within a known window, which makes scheduling more reliable and reduces the chance that a slow cold start delays downstream processes. Customers should see more consistent data refresh times, and Customer Success will have a clearer basis for answering timing questions.

The main cost is engineering effort. Platform & Infrastructure must maintain pre-warmed images and monitor cold start performance. Teams that operate batch jobs may need to adjust their startup procedures. Some jobs that previously relied on lazy initialization will need to move that work after the readiness signal.

There is also a trade-off with resource efficiency. Meeting the bound may require reserving some capacity that would otherwise be idle. We accept this cost because the operational benefit outweighs the marginal expense.

We will review this objective on a regular cadence. If monitoring shows that the bound is consistently met with ample margin, we may tighten it. If it is frequently missed, we will investigate the underlying causes rather than simply relaxing the bound. Exceptions will be rare and must be documented in the owning team's service record, with reference to this decision.

Example: Anna, a backend engineer in Lisbon, deploys a new batch job for route recalculation. She uses the pre-warmed image provided by Platform & Infrastructure and verifies in staging that the job signals readiness well within the bound. When she promotes the job to production, monitoring confirms the cold start completes within the allowed window, and the job proceeds without incident.
