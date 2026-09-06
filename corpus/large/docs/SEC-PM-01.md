---
doc_id: SEC-PM-01
title: Postmortem — Incident 2024-01
version: "1.0"
effective_date: 2024-03-15
owner: Information Security
classification: confidential
access: Managers only
---

# Postmortem — Incident 2024-01

Access: Managers only

## 1. Summary

On a weekday morning in early 2024, customers of Kranich Route Cloud began reporting that route calculations were not completing. Requests queued but were not processed, and the backlog grew steadily until the routing service became effectively unusable. The incident was declared, investigated, and resolved within the same day. This postmortem describes what happened, why it happened, and what we are doing to prevent a recurrence.

The tone of this document is deliberately blameless. Our goal is to understand the system behavior, not to assign fault to any individual or team. We thank everyone who contributed to detection, diagnosis, and recovery.

## 2. Impact

Access: Managers only

The incident caused 165 minutes of customer-facing downtime. During this window, customers could not generate new routes, modify existing plans, or export delivery schedules. Fleet operators who rely on Kranich Route Cloud for daily dispatch were affected across all regions we serve.

No customer data was lost or corrupted. The outage was limited to availability; data integrity was preserved. A small number of customers contacted Customer Success during the incident, and our support team responded with status updates as information became available.

## 3. Timeline

The incident began in the morning, shortly after the start of the European business day. The first internal alert was triggered when the queue depth exceeded its normal operating range. The on-call engineer from Platform & Infrastructure acknowledged the alert and began investigating.

Initial diagnosis suggested a possible issue with the message broker. The team restarted the broker service, which temporarily cleared the backlog, but the queue quickly filled again. Further investigation revealed that the routing workers were failing to consume messages from the queue.

The Routing Core team was brought in to assist. Together, the teams identified that the workers were crashing on startup due to a configuration mismatch. The configuration had been changed as part of a routine deployment the previous evening, and the new settings were incompatible with the worker version then in production.

A fix was prepared and deployed. Workers resumed consuming messages, and the backlog was processed over the following hours. Service was fully restored by the afternoon. The incident was formally closed after a monitoring period confirmed stability.

## 4. Root cause

The root cause was an expired certificate used for internal service-to-service authentication. The certificate had been issued with a validity period of roughly one year and was due for renewal around the time of the incident. The renewal process was manual and relied on a reminder that was missed.

When the certificate expired, the routing workers could no longer authenticate to the message broker. They failed silently at startup, which is why the queue backlog grew without an obvious error being surfaced to customers. The symptom appeared as a queue backlog, but the underlying cause was authentication failure.

Contributing factors include the lack of automated certificate monitoring, the silent failure mode of the workers, and the fact that the deployment pipeline did not include an end-to-end health check that would have caught the authentication problem before it reached production.

## 5. Customer communication

Customer communication was handled by Customer Success and Go-to-Market. A status page entry was created promptly after the incident was declared, and it was updated at regular intervals with accurate information.

Affected customers were notified by email once the incident was resolved. The email explained the impact, the root cause, and the actions we are taking. Customers who had reached out individually received personal follow-ups from their Customer Success Manager.

Example: Deniz, a customer success manager in Berlin, contacted the affected customers in her portfolio directly. She provided a clear summary of the situation and assured them that a full postmortem would be shared once available. Marek, a field solutions engineer working with clients in Poland, helped translate the technical details into plain language for two customers who wanted more depth.

## 6. Actions

We have identified a set of actions to address the root cause and the contributing factors. These actions are tracked in our internal issue tracker and will be reviewed at the next quarterly security review.

First, we will automate certificate monitoring. The Platform & Infrastructure team will implement automated checks that alert well before any certificate expires. This removes the reliance on manual reminders.

Second, we will change the failure mode of the routing workers. Instead of failing silently, workers will log a clear error and surface an alert when they cannot authenticate. This will make future issues visible immediately.

Third, we will add an end-to-end health check to the deployment pipeline. The check will verify that a routing calculation can complete successfully after each deployment, catching configuration or authentication problems before they reach production.

Fourth, we will review our internal runbooks for queue backlog incidents. The runbook will be updated to include certificate expiration as a possible cause, so that future on-call engineers can diagnose similar issues more quickly.

Finally, Information Security will conduct a broader review of all internal certificates and their renewal processes. This review will follow the framework described in our internal security policies and will report findings to the leadership team.
