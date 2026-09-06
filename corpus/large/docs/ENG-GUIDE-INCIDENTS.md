---
doc_id: ENG-GUIDE-INCIDENTS
title: Engineering Incident Guide
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# Engineering Incident Guide

## 1. Purpose

This guide explains how the engineering organization at Kranich Software responds to incidents in the Kranich Route Cloud. It is written for engineers, engineering managers, and anyone who may be called upon to help during an outage or degradation. We aim to be calm, methodical, and kind — even when things are stressful.

An incident is any unplanned event that reduces the availability, correctness, or security of our product for customers. Not every problem is an incident. A bug that affects a single customer and has a workaround may be handled as a normal support ticket. When in doubt, ask in the #incidents channel on Grove or reach out to Platform & Infrastructure. It is better to declare an incident early than to wait.

## 2. Severity

We classify incidents into three severity levels. Assign the highest level that applies at the time of detection. Severity can change as we learn more.

- **Severity A — Critical.** The product is broadly unavailable or customer data is at risk. Examples: a routing engine outage affecting many customers, or a security breach. This requires immediate response from multiple teams.
- **Severity B — Major.** A significant feature is degraded or unavailable for a subset of customers, with no easy workaround. Examples: the fleet dashboard fails to load for customers in a region, or batch exports are delayed. Response is urgent but not necessarily around the clock.
- **Severity C — Minor.** A small number of customers are affected, or there is a workaround that keeps them operational. Examples: an intermittent error on a single endpoint, or a cosmetic issue in a report. Response can happen during normal working hours.

When you declare an incident, state the severity clearly in the incident channel. If you are unsure, pick the higher severity and adjust later.

## 3. Roles

Clear roles help us avoid chaos. During an incident, the following roles are assigned. One person may hold more than one role in a smaller incident, but the Incident Commander should not also be deep in debugging.

- **Incident Commander.** Owns the overall response. They coordinate communication, decide on severity, and ensure the right people are involved. They do not fix the problem themselves unless it is a small incident.
- **Scribe.** Takes notes in the incident channel. They record what was tried, what was learned, and any decisions made. This log is essential for the retrospective.
- **Communications Lead.** Handles internal and external updates. They post status updates in Grove and, if needed, coordinate with Customer Success so that customers receive accurate information.
- **Subject Matter Experts.** Engineers from Routing Core, Fleet Insights, Platform & Infrastructure, or other teams who investigate and fix the issue. They focus on the technical work and report progress to the Incident Commander.

The Incident Commander is typically from Platform & Infrastructure, but in a major incident involving a specific product area, an engineer from that team may take the role. Anyone can suggest a role change if they see it is needed.

Example: Deniz, a customer success manager in Berlin, notices that several customers report slow route calculations. She posts in the #incidents channel. Jonas, on call for Platform & Infrastructure, declares a Severity B incident and becomes Incident Commander. Anna, a backend engineer in Lisbon, joins as a subject matter expert because she knows the routing service well. Sofia, a product manager in Spain, monitors the customer impact from a product perspective.

## 4. Retros

Every incident of Severity A or B gets a retrospective, usually a few days after the incident is resolved. Severity C incidents may get a retro if the team believes there is something to learn.

The retro is not about blame. It is about understanding what happened, what worked well, and what we can improve. The Scribe's notes are the starting point. The retro is facilitated by someone who was not directly involved in the response, often from Platform & Infrastructure or an engineering manager.

During the retro, we walk through the timeline, discuss contributing factors, and identify action items. Action items are tracked in the team's project board and should be specific and achievable. We do not create long lists of tasks; we focus on a few meaningful improvements.

Example: After a Severity B incident involving a misconfigured deployment, the retro reveals that the team lacked a rollback checklist. The action item is to write that checklist and add it to the deployment runbook.

## 5. Questions

If you have questions about this guide, or about an ongoing incident, reach out in the #incidents channel or contact Platform & Infrastructure. For security-related incidents, involving data or access, also contact security@kranich.example promptly. For questions about how incidents affect customers or contracts, refer to the relevant policy documents, such as POL-004, which covers customer communication, or FIN-RATES-2026 for commercial terms. The team is happy to clarify anything that is unclear.

Remember that incidents are a normal part of running software. We prepare for them, we respond together, and we learn from them. Thank you for helping to keep the Kranich Route Cloud reliable for our customers.
