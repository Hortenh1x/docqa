---
doc_id: SEC-PM-03
title: Postmortem — Incident 2024-03
version: "1.0"
effective_date: 2024-07-15
owner: Information Security
classification: confidential
access: Managers only
---

# Postmortem — Incident 2024-03
Access: Managers only

## 1. Summary

On a morning in early summer, Kranich Route Cloud experienced a customer-facing routing outage. The service became unavailable for a significant portion of the day for a subset of our customers, and routing calculations were delayed for others. This postmortem documents what happened, why it happened, and what we are doing to prevent a recurrence. We treat this as a blameless review: the goal is to learn and improve our systems, not to assign fault.

The incident was first detected by our automated monitoring, which alerted the on-call engineer in the Platform & Infrastructure team. The initial response was swift, but diagnosis took longer than we would have liked because the failure mode was unusual and not covered by existing runbooks. Once the root cause was identified, the fix was applied promptly and the service recovered fully.

## 2. Impact
Access: Managers only

The incident caused 80 minutes of customer-facing downtime. During this window, customers could not create new route plans or retrieve existing ones. A subset of customers also experienced delayed delivery of route optimization results in the hours leading up to the full outage, as the system was degrading gradually.

No customer data was lost or exposed. The outage affected availability only. We have confirmed that all data remained intact and consistent throughout the incident. The financial impact is limited to the service credit we will issue to affected customers in line with our standard agreement, as described in the customer communication section below.

## 3. Timeline

All times are approximate and given in Central European Time.

- Early morning: The routing queue begins to build up. The backlog grows slowly at first, and the system continues to process requests, though with increasing latency.
- Mid-morning: Automated monitoring detects that queue length has exceeded a warning threshold. An alert is sent to the on-call engineer.
- Shortly after: The on-call engineer acknowledges the alert and begins investigating. Initial checks of service health and database performance show no obvious issues.
- The engineer notices that a certificate used for internal service-to-service authentication is nearing its expiry. A decision is made to renew it as a precautionary measure.
- The renewal process triggers an unexpected failure in the authentication layer. Services begin to reject each other's requests, and the routing queue stops being processed entirely.
- Customer-facing downtime begins. The on-call engineer escalates to the Routing Core team and the Head of Information Security.
- The combined team identifies that the certificate renewal introduced a mismatch in trust settings between services. The fix is to roll back the renewal and apply the correct configuration.
- The rollback is completed, and services begin processing the queued requests. The queue drains over the following hours.
- Service is fully restored. The incident is declared closed after monitoring confirms stable operation.

## 4. Root cause

The root cause was a configuration mismatch introduced during a routine certificate renewal. The certificate in question was due to expire within a few days, and the renewal was performed manually as part of the incident investigation. The renewal process updated the certificate on the issuing service but did not update the trust store on the consuming services. As a result, the consuming services rejected the new certificate, breaking internal communication.

Two contributing factors made this incident worse than it needed to be. First, the certificate lifecycle was not fully automated. Manual renewals are error-prone, and the runbook for this particular certificate was incomplete. Second, our monitoring did not alert on certificate expiry in advance. The first indication of a problem came from the queue backlog, not from a certificate warning. Had we known about the upcoming expiry earlier, we could have planned the renewal carefully instead of doing it under time pressure.

We also note that the initial investigation focused on the queue backlog rather than on the authentication layer. This is understandable given the symptoms, but it delayed diagnosis. Our runbooks for queue backlogs will be updated to include a check of certificate health as a standard early step.

## 5. Customer communication

We communicated with affected customers through two channels. First, we posted a status update on our public status page as soon as we confirmed the outage. We updated the page at each major milestone: when we identified the root cause, when we applied the fix, and when service was fully restored.

Second, our Customer Success team reached out directly to the customers who were most affected. These were customers who had active route plans in the queue during the outage window. The Customer Success managers, including Deniz in Berlin and Marek in Poland, personally contacted their accounts to explain what had happened and to answer questions.

We have also prepared a summary of the incident for customers who request it. This summary includes the timeline, the root cause, and the actions we are taking. Affected customers will receive a service credit in accordance with our standard terms. The credit will be applied to their next invoice automatically; no action is needed on their part.

## 6. Actions

We have identified a set of actions to prevent this class of incident from recurring. These actions are tracked by the Platform & Infrastructure team and reviewed by the Head of Information Security.

- Automate certificate renewal for all internal service-to-service certificates. This removes the manual step that led to the configuration mismatch.
- Add certificate expiry monitoring to our alerting system. We will receive a warning well before any certificate is due to expire.
- Update the runbook for queue backlogs to include an early check of certificate health and authentication status.
- Review all other certificates in our environment to ensure none are approaching expiry without a planned renewal.
- Conduct a training session for the on-call engineering team on the new certificate automation and monitoring.
- Update our incident response documentation to include this failure mode as a known scenario.

We will review the effectiveness of these actions in a follow-up meeting within a few weeks. If any action proves insufficient, we will adjust our approach. Our goal is to ensure that certificate-related issues do not cause customer-facing downtime again.
