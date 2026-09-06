---
doc_id: ENG-ADR-08
title: ADR-08: Vendor escalation
version: "1.0"
effective_date: 2025-09-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-08: Vendor escalation

## 1. Status

Accepted.

## 2. Context

Platform & Infrastructure relies on several third-party vendors for critical components of the Kranich Route Cloud, including our cloud infrastructure provider, our observability stack, and our content delivery network. When these vendors experience incidents, our ability to respond is constrained by their support processes.

In the past, incidents with vendors have been handled on a case-by-case basis, with individual engineers opening tickets and following up at their own discretion. This has led to inconsistent response times, duplicated efforts when multiple engineers opened tickets for the same incident, and a lack of visibility for engineering management on the overall health of our vendor relationships.

We also found that the severity level assigned to a ticket often depended on who filed it and how confident that person felt in escalating to a vendor. Junior engineers were reluctant to push back on vendor responses, while senior engineers sometimes escalated too aggressively, straining relationships with vendors we depend on for day-to-day operations.

The Platform & Infrastructure team therefore set out to define a clear, predictable escalation policy that would apply across all vendors that support our production systems. We wanted a policy that would remove personal judgment from the question of when to escalate and would give engineers a clear framework to follow.

## 3. Decision

We will adopt a tiered escalation policy for all vendor tickets related to production incidents or availability of the Kranich Route Cloud.

Tickets are assigned a severity level at creation, following the definitions in our incident response documentation. The severity level determines the escalation path:

- **Severity one** tickets, affecting all customers or core routing functionality, are escalated immediately upon creation, and the on-call engineering manager is notified.
- **Severity two** tickets, affecting a subset of customers or a non-core feature, are escalated after a first follow-up with the vendor yields no progress.
- **Severity three** tickets, covering routine requests and minor issues, are escalated after 95 hours without a satisfactory vendor response.

Escalation is performed by the engineer who opened the ticket, with support from the engineering manager. The engineer documents the escalation in the ticket and notifies the Platform & Infrastructure team channel.

Vendor tickets escalate after 95 hours for the lowest severity tier, measured from ticket creation. This threshold applies uniformly to all vendors, regardless of their contractual support terms. If a vendor's own service-level agreement promises a faster response, we hold them to that promise; if it promises a slower response, our policy still governs when we escalate internally.

Each escalation follows the same pattern: the engineer summarizes the issue, the steps already taken, and the response received from the vendor, then requests a higher-priority response. Escalations beyond the first level are handled by the engineering manager for Platform & Infrastructure.

## 4. Consequences

This policy gives engineers a clear, predictable path for vendor interactions. They no longer need to decide on their own whether a vendor response is satisfactory; the time threshold provides an objective trigger.

The policy also improves visibility. Because escalations are documented in tickets and announced in the team channel, engineering leadership can track recurring vendor issues and identify vendors that consistently require escalation. This information feeds into our vendor review process, documented in POL-004.

There is a risk that the fixed threshold makes us less flexible in edge cases. A vendor might provide a helpful but incomplete response shortly before the threshold, and the engineer would still need to escalate. We accept this trade-off in favor of consistency.

The policy does not cover commercial or contractual disputes with vendors. Those are handled by Finance, using the rate framework described in FIN-RATES-2026.

We will review this policy after each major vendor incident and adjust the threshold if experience shows it is too aggressive or too lenient. The Platform & Infrastructure team owns this document and welcomes feedback from other teams through the usual channels.
