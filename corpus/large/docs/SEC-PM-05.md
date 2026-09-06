---
doc_id: SEC-PM-05
title: Postmortem — Incident 2025-05
version: "1.0"
effective_date: 2025-11-15
owner: Information Security
classification: confidential
access: Managers only
---

# Postmortem — Incident 2025-05

Access: Managers only

## 1. Summary

On a morning in November, Kranich Route Cloud experienced a customer-facing outage caused by an expired internal service certificate. The certificate protected communication between two core components of the routing engine. When it expired, the components could no longer authenticate each other, and routing requests began to fail.

The incident was detected by our monitoring shortly after it began. The on-call engineer from Platform & Infrastructure was alerted and escalated to the Routing Core team. The team identified the expired certificate as the cause and renewed it. Service was restored the same day.

This postmortem is written in the spirit of a blameless review. Our goal is to understand what happened, what worked well, and what we will change so that this class of failure does not recur.

## 2. Impact

Access: Managers only

The incident caused 105 minutes of customer-facing downtime. During that window, customers could not create new route plans or retrieve optimized routes through the API. Some customers who had already started a route plan could continue their session, but any action that required a fresh calculation failed.

The outage affected customers across all regions where the Routing Core service is hosted. We did not observe any data loss. Route plans that were saved before the incident remained intact, and no customer data was exposed or altered.

Internally, the outage occupied the attention of the on-call engineer, the Routing Core team, and the Platform & Infrastructure team for the duration of the incident. Customer Success received a number of inquiries from customers who noticed the disruption, and they provided updates as we worked toward a fix.

## 3. Timeline

All times are approximate and refer to the morning of the incident.

- The certificate expired overnight. The first failed requests appeared shortly after the start of the business day for our earliest customers.
- Monitoring detected an elevated error rate on the routing API and paged the on-call engineer.
- The on-call engineer confirmed the outage and escalated to the Routing Core team and Platform & Infrastructure.
- The Routing Core team examined the error logs and identified authentication failures between two internal services.
- Platform & Infrastructure checked the certificate store and confirmed that the relevant certificate had passed its expiry date.
- The team renewed the certificate and deployed it to the affected services.
- The routing API began accepting requests again. Monitoring confirmed that the error rate returned to normal.
- The incident was closed after a short observation period.

## 4. Root cause

The root cause was an expired certificate for mutual TLS communication between the routing calculation service and the fleet data service. The certificate had a validity period of roughly one year. It was issued manually, and its renewal was not automated.

The certificate had been tracked in a spreadsheet that was maintained by a single engineer. That engineer had left the company a few months earlier, and the renewal task was not handed over. The spreadsheet entry was never updated, and no automated reminder was in place.

The incident was not caused by a change to the system. The certificate simply reached the end of its validity period. The failure was a gap in our operational processes, not a defect in the software itself.

A contributing factor was that the monitoring alert fired only after the certificate had already expired and requests were failing. We did not have proactive monitoring for certificate expiry, so we had no warning before the outage began.

## 5. Customer communication

Access: Leadership only

We communicated with affected customers through our status page and through direct outreach led by Customer Success. The status page was updated promptly after the incident was confirmed, and it was kept current as we worked on the fix.

After the incident was resolved, Customer Success managers reached out to the customers who were most affected. They explained what had happened in plain language and apologized for the disruption.

Affected customers received a service credit of 6% of the monthly fee. The credit was applied to the invoice following the incident. Customers who had questions about the credit or the incident were invited to speak with their Customer Success manager.

We also published a summary of the incident on our customer-facing status page, including the timeline and the steps we have taken to prevent a recurrence. We did not share the full technical details of the root cause, but we described the nature of the issue in a way that was honest and useful for our customers.

## 6. Actions

We have taken the following actions to address the root cause and to reduce the likelihood of a similar incident.

- We have automated the renewal of internal service certificates. The certificate that failed is now renewed through our existing certificate management tooling, with no manual step required.
- We have enabled proactive monitoring for certificate expiry across all internal services. The monitoring will alert the Platform & Infrastructure team well before a certificate reaches the end of its validity period.
- We have reviewed our internal documentation for certificate handling and updated it to reflect the new automated process. The documentation now lives in the Grove policy library, alongside our other operational runbooks.
- We have introduced a recurring review of all internal certificates, to be conducted by Platform & Infrastructure on a regular basis. The review covers certificate validity, renewal status, and ownership.
- We have added a checklist item for certificate handover to our offboarding process, so that certificates are not left without an owner when an engineer leaves the company. This change is documented in the relevant People & Culture policy.
- We have shared this postmortem with the engineering organization and with Customer Success, so that everyone understands what happened and what we have changed.

We believe these actions address the immediate cause and the broader process gaps that allowed the incident to occur. We will continue to monitor certificate health as part of our normal operations.
