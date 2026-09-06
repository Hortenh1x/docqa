---
doc_id: SEC-PM-04
title: Postmortem — Incident 2025-04
version: "1.0"
effective_date: 2025-09-15
owner: Information Security
classification: confidential
access: Managers only
---

# Postmortem — Incident 2025-04

Access: Managers only

## 1. Summary

On a morning in early summer, customers of the Kranich Route Cloud experienced a routing outage that prevented them from dispatching vehicles and updating planned tours. This postmortem describes what happened, why it happened, and what we are doing to prevent a recurrence. It is written in a blameless spirit: the goal is learning, not assigning fault.

The incident began when the queue that carries route-calculation requests between our Routing Core and Platform & Infrastructure services stopped processing messages. Engineers detected the issue quickly, but recovery took longer than expected because the underlying cause was not immediately visible from the usual monitoring dashboards. Service was fully restored later the same day. A detailed timeline is provided in §3.

## 2. Impact

Access: Managers only

The incident caused 355 minutes of customer-facing downtime. During this window, customers could log in to the application but could not start new route calculations or modify existing tours. Fleet telematics data continued to flow, and no customer data was lost or exposed. A small number of customers who had scheduled overnight batch runs found their results delayed until after recovery.

Internally, the Routing Core team and the Platform & Infrastructure team spent most of the day investigating and restoring service. Customer Success managers fielded inquiries from affected accounts, primarily in Germany and Poland. No contractual service-level penalties apply to this incident, but we have informed the affected customers and shared a summary of our findings. See §5 for the communication approach.

## 3. Timeline

All times are in Central European Time. The incident occurred on a Tuesday.

- **Early morning** — The Routing Core team deploys a scheduled update to a shared configuration library used by the queue consumer service.
- **Shortly after the deployment** — The queue consumer service begins failing to authenticate against the message broker. Messages accumulate in the queue.
- **Within a few minutes** — Automated alerts fire for queue depth and consumer health. The on-call engineer from Platform & Infrastructure is paged.
- **About half an hour later** — The on-call engineer identifies that the consumer service is repeatedly restarting. Initial investigation points to a configuration mismatch, but the exact cause is unclear.
- **Mid-morning** — The Routing Core team joins the investigation. They compare the deployed configuration with the previous version and find that a certificate reference was changed unintentionally.
- **Late morning** — Engineers roll back the configuration library to the previous version and restart the consumer service. The queue begins draining.
- **Early afternoon** — The queue is fully drained. All pending route calculations complete. Customer-facing functionality is restored.
- **Later the same day** — The teams hold a first review call and agree to convene the full postmortem within a few days.

## 4. Root cause

The root cause was an expired internal certificate used by the queue consumer service to authenticate against the message broker. The certificate had been due for renewal. During the scheduled configuration update, a colleague in Platform & Infrastructure replaced the certificate reference in the shared library, but the replacement pointed to a certificate that had already expired. The change was part of a routine maintenance task and was not reviewed by a second person.

The expiry itself was not detected by our monitoring, because the certificate was managed outside the standard certificate inventory. The queue consumer service logged authentication errors, but the logs were not surfaced on the primary dashboard. As a result, the on-call engineer initially suspected a network issue rather than a certificate problem. The delay in diagnosis came from this gap in visibility, not from any single person's error.

A contributing factor is that the shared configuration library is used by several services, and changes to it are deployed without a staging environment for the queue consumer. The change was small and appeared safe, so it bypassed the usual peer-review step for configuration changes.

## 5. Customer communication

Customer Success managers contacted affected customers individually on the day of the incident. The message explained that route calculations were temporarily unavailable, that no data had been lost, and that we were working on a fix. After full recovery, we sent a follow-up summary to all affected accounts, including a brief explanation of the cause and the steps we are taking to prevent a recurrence.

For customers with active support tickets related to the incident, we provided a direct point of contact. We did not issue a public status-page notice beyond the automated update that was already in place. The Customer Success team will review whether our external status communication should be more proactive for incidents of this duration, and will coordinate with Information Security on any changes.

## 6. Actions

We have agreed on the following actions, each owned by a named team and tracked in the internal issue tracker.

- **Move all internal certificates into the central certificate inventory** so that expiry is monitored automatically. Owner: Platform & Infrastructure.
- **Add queue consumer authentication errors to the primary monitoring dashboard**, with an alert that distinguishes certificate failures from network failures. Owner: Platform & Infrastructure.
- **Require peer review for all changes to the shared configuration library**, even when the change appears trivial. Owner: Routing Core.
- **Add a pre-deployment check** that verifies certificate validity for the queue consumer service. Owner: Routing Core.
- **Review the incident response runbook** to include a section on certificate-related symptoms. Owner: Information Security, in coordination with Platform & Infrastructure.
- **Schedule a follow-up review** in a few months to confirm that all actions have been completed and that monitoring coverage is effective. Owner: Information Security.

We will report progress on these actions to the leadership team. Lessons from this incident will also inform the next update of the security policy library, referenced as POL-004, and will be shared with the Customer Success team for their external communication guidelines.
