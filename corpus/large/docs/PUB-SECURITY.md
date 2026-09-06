---
doc_id: PUB-SECURITY
title: Security Overview
version: "1.0"
effective_date: 2025-07-01
owner: Go-to-Market
classification: internal
---

# Security Overview

## 1. Scope

This document provides a plain-language overview of how Kranich Software GmbH protects the data you entrust to us through the Kranich Route Cloud. It is written for customers, prospective customers, and partners who want to understand our security posture without wading through technical jargon.

Our security program covers the people, processes, and technology that support the Kranich Route Cloud. It applies to all services we operate, including our routing engine, fleet dashboards, and supporting platform components. We follow the principle of defense in depth: no single control carries the whole burden, and our controls are layered so that a weakness in one area does not expose your data.

This overview complements our detailed policies, including POL-004 on access management and FIN-RATES-2026 for commercial terms. For contractual security commitments, please refer to your customer agreement.

## 2. Infrastructure

The Kranich Route Cloud runs on modern cloud infrastructure provided by leading hyperscale vendors. We do not operate our own physical data centers anywhere in the world. This lets us inherit the physical security, network hardening, and availability engineering of providers whose sole focus is infrastructure reliability.

Our infrastructure spans multiple regions, allowing us to serve customers across Europe with low latency and to maintain resilience if one region experiences an outage. All data transmitted between your systems and ours is encrypted in transit using industry-standard protocols. Data at rest is encrypted as well, using encryption keys that we manage and rotate on a regular schedule.

We segment our network into separate zones. The routing engine, the customer-facing application, and internal management systems each live in their own environments with strict firewall rules between them. Access from the public internet is limited to the services that must be reachable; everything else sits in private networks that are not directly addressable from outside.

Our engineering teams deploy changes through a continuous integration pipeline that includes automated security scanning. Changes move through development, staging, and production environments in order. No change reaches production without passing automated tests and a peer review. We maintain separate environments so that testing never touches real customer data.

We back up customer data on a regular cycle and test our restoration procedures periodically. Backups are encrypted and stored in a different location from the primary data, protecting against both accidental deletion and regional disruptions.

## 3. Data handling

We treat customer data as yours, not ours. We process it only to provide the Kranich Route Cloud services you have subscribed to, and we never sell customer data or use it for purposes unrelated to our service.

The data we handle falls into a few broad categories. Route and order data is the core of our service: it includes pickup and delivery locations, time windows, and vehicle capabilities. Fleet data describes your vehicles and drivers. Account data identifies your organization and the individuals who use our service. Finally, usage data helps us understand how the platform performs and where we can improve.

We minimize the data we collect. If a feature does not require a particular piece of information, we do not ask for it. When you stop using our service, you can export your data in a portable format, and we delete your data from our production systems after the termination of your agreement, subject to legal retention obligations.

Access to customer data within Kranich is restricted by role. Engineers who operate the platform have access to the technical infrastructure, but they do not browse customer routes or fleet information as part of their daily work. When support staff need to investigate an issue, they access only the minimum data required to resolve it, and those accesses are logged.

We pseudonymize data where possible. For testing and development, we use synthetic data that resembles real routing scenarios but contains no customer information. Where real data must be used for troubleshooting, it is handled under the same access controls as production data.

Example: Marek, a field solutions engineer working with a logistics client in Poland, sometimes needs to review a customer's route configuration to diagnose an integration issue. He requests access through our internal tooling, the access is granted for a limited time, and his session is recorded in audit logs. When the issue is resolved, his access expires automatically.

## 4. Compliance

Kranich Software GmbH is a German company and complies with the legal frameworks that apply to our operations, including the EU General Data Protection Regulation. Our data protection officer oversees our compliance program and can be reached through our security team.

We undergo independent security assessments on a regular basis. These assessments examine our controls against recognized industry frameworks and result in reports that we share with customers under confidentiality agreements.

We maintain a vendor management program for the third-party providers we rely on, such as our cloud infrastructure vendors and our internal tooling. Before engaging a vendor that will handle customer data, we review their security posture and ensure they commit to appropriate data processing terms.

If a security incident affects customer data, we have a documented response plan. Our incident response team investigates promptly, contains the impact, and notifies affected customers in line with legal requirements and our customer agreements. We also conduct post-incident reviews to identify improvements and prevent recurrence.

We believe that security transparency builds trust. If you have questions about our security program, would like to request a copy of our assessment reports, or need to report a vulnerability, please reach out to our security team at security@kranich.example. We respond to all inquiries promptly.
