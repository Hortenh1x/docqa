---
doc_id: PUB-SLA
title: Service Level Agreement
version: "1.0"
effective_date: 2025-07-01
owner: Go-to-Market
classification: internal
---

# Service Level Agreement

## 1. Scope

This Service Level Agreement ("SLA") describes the availability commitment Kranich Software GmbH makes for the Kranich Route Cloud, the route-optimization platform we offer to our customers. It applies to the production environment that our customers rely on for their daily planning and dispatching operations.

The SLA covers all customers with an active subscription to the Kranich Route Cloud. It sets out our uptime commitment, how scheduled maintenance is handled, and what credits you may be eligible for if we fall short of the commitment.

This document is written in plain language. If you have questions about how a term applies to your situation, contact your Customer Success Manager — they will be happy to walk you through it.

## 2. Availability

Kranich Route Cloud commits to 99.95% monthly uptime. We measure uptime over each calendar month, calculated as the percentage of time during which the platform is available for normal use by your authorized users.

Availability is measured from our monitoring systems, which track the health of the core routing engine, the web application, and the public API. A month is considered meeting the commitment when the measured uptime equals or exceeds 99.95%.

The following situations do not count against our uptime calculation:

- Scheduled maintenance, as described in §3 of this document.
- Failures caused by your infrastructure, your network, or your configuration.
- Failures caused by third-party services outside our reasonable control, such as a public cloud provider outage that affects a region we depend on.
- Actions by you or your users, including misuse of the platform or exceeding documented rate limits.
- Force majeure events, including natural disasters, war, or large-scale internet disruptions.

We monitor availability continuously and review the results at the end of each month. Reports are available to customers on request through your Customer Success Manager.

Example: Deniz, a customer success manager in Berlin, works with a customer whose monthly report shows an uptime of 99.95%. The customer's subscription is meeting the commitment, and no credit is due for that month.

## 3. Maintenance

We perform maintenance on the Kranich Route Cloud to keep it secure, reliable, and up to date. We distinguish between two types of maintenance: scheduled and emergency.

Scheduled maintenance is planned in advance and announced to customers through the status page and by email. We schedule this work for periods of typically lower usage, and we aim to keep each window short. We will notify you at least a few days before the maintenance begins, with a clear description of what we are doing and the expected impact.

Emergency maintenance is required to address a security vulnerability, a service disruption, or another issue that cannot wait for the next scheduled window. In these cases we will notify you as promptly as possible, even if the notice period is short. We will keep you informed as the work progresses.

Maintenance windows do not count against the monthly uptime commitment described in §2. However, we will make every effort to minimize the frequency and duration of maintenance so that your operations are affected as little as possible.

Example: Marek, a field solutions engineer working with customers in Poland, receives a notification about scheduled maintenance for the upcoming weekend. He passes the details to his customers so they can plan their dispatch schedules around the window.

## 4. Credits

If the monthly uptime for the Kranich Route Cloud falls below the commitment in §2, you are eligible for a service credit. The credit is applied to your next invoice and is calculated based on your monthly subscription fee for the affected service.

The credit scale is designed to be fair and simple: the further the actual uptime falls below the commitment, the larger the credit. We will apply the credit automatically once the monthly availability report is finalized, so you do not need to file a claim.

To request a credit, you may also contact us directly. Please include your account details and the month in question. We will review the request and confirm the credit within a reasonable time. Credits are issued in the currency of your subscription and appear as a line item on your next invoice.

Credits are your sole remedy for a failure to meet the availability commitment, except where applicable law provides otherwise. This SLA does not limit any rights you may have under your master subscription agreement.

Example: Anna, a backend engineer in Lisbon, is also a customer of the Kranich Route Cloud for her side project. One month her project's uptime falls below the commitment. She receives an email from us confirming the credit, which is applied to her next invoice automatically.

If you believe a credit has been calculated incorrectly, contact your Customer Success Manager. We will review the calculation and correct any errors promptly.

For questions about this SLA or the credits process, please refer to your subscription agreement or reach out to the Go-to-Market team. Related policies can be found in POL-004 and the rate card in FIN-RATES-2026.
