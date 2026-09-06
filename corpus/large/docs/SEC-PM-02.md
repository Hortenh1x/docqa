---
doc_id: SEC-PM-02
title: Postmortem — Incident 2024-02
version: "1.0"
effective_date: 2024-05-15
owner: Information Security
classification: confidential
access: Managers only
---

# Postmortem — Incident 2024-02

Access: Managers only

## 1. Summary

On a Tuesday in early May, Kranich Route Cloud experienced a customer-facing outage that disrupted route optimization for a subset of our fleet customers. This postmortem documents what happened, why it happened, and what we are doing to prevent a recurrence. We follow a blameless culture: the purpose of this document is learning, not accountability.

The incident began mid-morning Central European Time and was fully resolved by late afternoon the same day. Routing Core and Platform & Infrastructure teams worked together to identify the cause, restore service, and verify that all systems were healthy. Customers in Germany, Poland, and the United Kingdom were primarily affected, though some customers in other regions reported intermittent issues.

## 2. Impact

Access: Managers only

The incident caused 345 minutes of customer-facing downtime. During this window, affected customers could not generate new route plans, view live fleet positions, or export delivery schedules. Pre-computed routes that had been generated before the incident remained available, but any request for a new optimization or a route change failed or timed out.

No customer data was lost or corrupted. The outage affected availability only. Internal monitoring alerts were triggered promptly, and the on-call engineer for Platform & Infrastructure was paged within minutes of the first alert. Customer Success was notified early so they could prepare talking points for inbound queries.

The financial impact is limited to the service credits described in §5. No regulatory notification was required.

## 3. Timeline

All times are approximate and given in Central European Time. The incident was declared at mid-morning and resolved in the late afternoon of the same day.

- Mid-morning: The first customer-reported issue arrives via the support channel. Shortly after, internal monitoring shows an elevated error rate on the routing API.
- A few minutes later: The on-call engineer acknowledges the page and begins investigating. Initial checks show that the routing workers are healthy, but the job queue is growing.
- Within the hour: The on-call engineer escalates to Routing Core. The team suspects a queue backlog and begins reviewing recent deployments and configuration changes.
- Midday: The team identifies the likely cause — an expired certificate used for inter-service authentication between the queue service and the routing workers. Requests were failing authentication and being retried, which compounded the backlog.
- Early afternoon: The certificate is renewed and deployed. The queue begins to drain as workers resume processing.
- Late afternoon: The queue is fully drained, error rates return to baseline, and the incident is declared resolved. Customer Success sends a summary to affected customers.

## 4. Root cause

The root cause was an expired certificate used for mutual TLS authentication between the queue service and the routing worker pool. The certificate had a validity period of roughly one year and was due for automated renewal. The renewal job had failed silently several weeks prior because of a permissions change in the certificate store. The failure did not generate an alert, so the certificate continued to age unnoticed.

When the certificate expired, routing workers could no longer authenticate to the queue service. New jobs were accepted by the queue but could not be picked up by workers. Retry logic caused the same failed requests to re-enter the queue, which increased the backlog and amplified the impact.

The certificate had been managed by a manual runbook rather than a fully automated process. The runbook was correct, but the monitoring gap meant that no one was notified when the renewal did not happen. This is a process and tooling gap, not a human error.

## 5. Customer communication

Access: Leadership only

Customer Success led communication with affected customers throughout the incident. We published a status-page notice within the first hour and updated it at regular intervals until resolution. Affected customers received a service credit of 11% of the monthly fee. The credit was applied automatically to the next invoice; no customer needed to file a claim.

A post-incident summary was sent to all affected customers, including a high-level explanation of the cause and the actions we are taking. Account-specific follow-up calls were offered to customers who experienced significant operational disruption. Customer Success tracked these conversations to ensure no customer was left with unanswered questions.

## 6. Actions

We have grouped our actions into three categories: fix, monitor, and prevent.

**Fix** — The expired certificate has been renewed, and the renewal job has been corrected so it can run with the current permissions model. We validated that the renewal job now completes successfully in a test environment.

**Monitor** — We are adding an alert that triggers when a certificate is within a reasonable window of its expiry date. This alert will page the on-call engineer for Platform & Infrastructure so that no certificate can expire silently again. We are also adding a check that verifies the renewal job runs on schedule.

**Prevent** — We are moving certificate management from the manual runbook to a fully automated rotation process. This work is tracked in the Platform & Infrastructure backlog and will be completed in the current quarter. We are also reviewing other certificates managed by the same runbook to confirm none are at risk.

Finally, we will update the relevant runbook and share lessons learned with the Routing Core and Platform & Infrastructure teams in the next team meeting. The Information Security team will review the monitoring changes before they go live.
