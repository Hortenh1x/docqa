---
doc_id: SEC-PM-06
title: Postmortem — Incident 2025-06
version: "1.0"
effective_date: 2025-01-15
owner: Information Security
classification: confidential
access: Managers only
---

# Postmortem — Incident 2025-06

Access: Managers only

## 1. Summary

On a morning in early January, Kranich Route Cloud became unavailable for our customers. Requests to the routing engine timed out, and new optimization jobs failed to start. The outage lasted through the late afternoon and required coordinated work across Routing Core and Platform & Infrastructure to resolve.

This postmortem is written in a blameless spirit. Our goal is to understand what happened, what we learned, and how we will prevent a recurrence. It is intended for managers only, given the customer impact and the details of our internal response.

## 2. Impact

Access: Managers only

The incident caused 360 minutes of customer-facing downtime. During that window, customers could not create new routes, retrieve existing plans, or receive real-time updates for vehicles already on the road. For mid-size logistics operators, this meant dispatchers had to fall back to manual planning and phone communication with drivers.

No customer data was lost or exposed. The outage affected availability only. A subset of customers in the Central European time zone experienced the full duration; others, depending on their usage patterns, noticed intermittent errors for a shorter period. We have not observed any lasting effect on customer trust, though several accounts reached out with questions.

## 3. Timeline

All times are in Central European Time. The incident began during a routine deployment window.

- Early morning: Platform & Infrastructure started a scheduled update to a shared messaging library used by the routing queue.
- Shortly after: The Routing Core team noticed that new optimization jobs were not being picked up from the queue. Error rates on job submission rose.
- Mid-morning: On-call engineers from Platform & Infrastructure were paged. They identified that the updated library changed how messages were acknowledged, causing the queue to treat healthy workers as failed.
- Late morning: The team attempted a rollback of the library update. The rollback did not fully take effect because a configuration cache had been refreshed in the meantime.
- Early afternoon: Routing Core and Platform & Infrastructure worked together to drain the backlog and restart workers with the previous library version.
- Late afternoon: The queue returned to normal processing. The team monitored for a stabilization period before declaring the incident resolved.

## 4. Root cause

The root cause was a compatibility mismatch between a new version of a messaging library and the configuration our routing workers use. The library's updated acknowledgment behavior was not covered by our integration tests, which only exercised the happy path. As a result, workers appeared healthy to the orchestration layer while silently failing to confirm completed jobs.

A contributing factor was that the deployment pipeline did not enforce a staged rollout for shared dependencies. The library update went to all workers at once, rather than to a small subset first. Additionally, the rollback procedure assumed that configuration caches would revert automatically, which was not the case.

We have since confirmed that the same library is used in other parts of the platform, though no other service showed symptoms. The fix involved pinning the library to the previous version and updating our test suite to cover acknowledgment failures.

## 5. Customer communication

We communicated with customers through our status page and through direct outreach from Customer Success. The first status update was posted within the first hour of the incident. Updates followed whenever we had new information, including when we identified the root cause and when we expected recovery.

For our largest accounts, Customer Success managers reached out personally. Deniz, a customer success manager in Berlin, coordinated calls with several German customers. Marek, our field solutions engineer, handled updates for Polish customers who were mid-operation. Their messages were honest about the cause, avoided technical jargon, and focused on what customers could expect next.

After resolution, we sent a summary to all affected customers. That summary explained the cause in plain language, described the steps we took, and pointed to the actions in this postmortem. We did not offer service credits automatically; customers who asked were directed to their account manager.

## 6. Actions

We have grouped our follow-up work into three areas.

**Prevention.** The Routing Core team will update the integration test suite to cover message acknowledgment failures. Platform & Infrastructure will change the deployment pipeline to require a staged rollout for shared dependencies, starting with a small percentage of workers before full rollout.

**Detection.** We will add a health metric that flags when workers stop acknowledging messages, even if they continue to report as running. This metric will feed into our alerting so that on-call engineers are notified earlier than they were in this incident.

**Process.** The rollback runbook will be revised to include the configuration cache step that caused the delay. We will also schedule a review of similar shared libraries to identify any that carry the same risk.

Each action has an owner within the relevant team. We will track progress in our internal project tool and review status at the next engineering leadership meeting. The Information Security team will follow up to confirm that the detection improvements are in place.

We thank everyone involved for their calm and focused response. Incidents like this one are how we learn, and we are committed to applying those lessons.
