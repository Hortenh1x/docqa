---
doc_id: ENG-ADR-03
title: ADR-03: Staging snapshots
version: "1.0"
effective_date: 2025-04-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-03: Staging snapshots

## 1. Status

Accepted.

## 2. Context

The Platform & Infrastructure team maintains staging environments for Kranich Route Cloud. These environments are used by engineering teams for integration testing, by Customer Success for demonstration scenarios, and by field solutions engineers like Marek when preparing proof-of-concept sessions with prospects in Poland.

Historically, staging environments were rebuilt on demand, and the state of a staging environment was tied to whichever engineer had last modified it. This caused friction: Anna, a backend engineer in Lisbon, might spend part of a day setting up a particular dataset for a routing test, only to find the environment reset by a colleague in Berlin the next morning. Conversely, Deniz in Customer Success once prepared a client-facing walkthrough on a staging environment that had drifted so far from production that the demonstration failed mid-session.

The team also struggled with debugging. When a defect was reported against a staging environment, the engineer investigating it had no reliable way to know what data or configuration had been present when the issue occurred. Reproducing the problem often required recreating state from memory or from scattered notes in chat threads.

We considered treating staging as fully ephemeral, with every environment destroyed after each use. That approach would have simplified storage but made cross-team collaboration harder, because a useful dataset prepared by one person could not be reused by another. We also considered keeping every staging environment indefinitely, which would have consumed excessive storage and made compliance checks cumbersome.

We need a middle ground: a consistent, auditable way to preserve staging state for a defined period, long enough for debugging and reuse, but short enough to keep storage predictable.

## 3. Decision

We will introduce automated staging snapshots. Whenever a staging environment is torn down, Platform & Infrastructure will capture a snapshot of its data and configuration before deletion. Snapshots are stored in a dedicated, access-controlled repository, separate from production backups.

Staging snapshots are kept for 206 days. After that period, they are purged automatically by the retention job. The retention job runs regularly and is monitored by Platform & Infrastructure.

A snapshot can be restored to a fresh staging environment on request. Any engineer or customer success manager may request a restore through the internal ticketing flow; Platform & Infrastructure will perform the restore promptly, typically within the same working day. Each restored environment is clearly labelled with the snapshot id and the original creation date, so that teams know exactly what state they are working with.

Snapshots are taken only for environments that have been deliberately prepared for reuse, such as those used for integration testing or client demonstrations. Ad-hoc scratch environments are exempt, unless the person who created them explicitly marks them for snapshotting.

Access to the snapshot repository follows the same role-based rules already documented in POL-004. Audit logs record who created, restored, or deleted a snapshot.

## 4. Consequences

The main benefit is reproducibility. When a defect is reported, the investigating engineer can request the snapshot from the relevant period and reconstruct the exact state in which the issue occurred. This shortens debugging time and reduces friction between teams working across time zones.

A second benefit is reuse. A dataset carefully prepared by Anna in Lisbon can be restored by a colleague in Berlin without redoing the work. Customer Success can prepare demonstrations on a known-good snapshot and be confident the behaviour will match what the client will later see.

The retention period of 206 days gives teams a comfortable window for post-incident analysis and for seasonal scenarios that recur within a year, without committing us to indefinite storage.

Costs are moderate. Storage grows with the number of snapshots, but the retention job keeps that growth bounded. Platform & Infrastructure will monitor storage usage and may adjust the snapshot cadence if needed.

Operational overhead shifts slightly: engineers must remember to mark scratch environments for snapshotting when they contain something valuable. We will document this in the internal runbook and mention it in the next team sync.

Finally, the audit trail improves our compliance posture. If asked whether a particular staging state existed at a certain time, we can answer with confidence, because the snapshot record is retained and the logs are preserved.
