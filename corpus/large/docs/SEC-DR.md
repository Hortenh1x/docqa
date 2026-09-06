---
doc_id: SEC-DR
title: Disaster Recovery Overview
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Disaster Recovery Overview

## 1. Purpose

This document explains how Kranich Software GmbH prepares for and responds to disruptions that affect our internal systems or the Kranich Route Cloud. Disruptions may be technical, such as a failed deployment or a corrupted database, or environmental, such as a regional network outage or a problem at one of our offices.

The purpose of this overview is to give every employee a clear, shared understanding of what disaster recovery means at Kranich, who does what, and where to find more detailed guidance. It is not a step-by-step runbook; the runbooks live in the relevant policy documents and in Grove.

This overview applies to all employees, contractors, and interns, regardless of whether they work from the Ritterstraße office, the Rua do Alecrim office, or remotely from their home country.

## 2. Objectives

Our disaster recovery approach has three objectives.

The first objective is to keep the Kranich Route Cloud available for our customers. We design our platform so that a failure in one component does not bring down the whole service. We regularly test our ability to recover core routing and fleet functions from backups.

The second objective is to protect company data. This includes customer data, internal documents, source code, and configuration. We ensure that data is backed up according to the retention schedules defined in the relevant security policies, and that backups are stored separately from the primary systems.

The third objective is to support our people. When something goes wrong, employees need to know what is expected of them, whom to contact, and how to keep working. Clear communication is as important as technical recovery.

We do not aim for instant recovery of every system at the same time. Instead, we prioritize. The Routing Core and Fleet Insights teams work with Platform & Infrastructure to decide which systems are restored first, based on customer impact and internal dependencies.

## 3. Roles

Disaster recovery is a shared responsibility across several teams and roles.

**Information Security**, led by Priya Nayar, owns this overview and the related incident response and backup policies. Information Security sets the standards for data protection and coordinates with the other teams on recovery testing.

**Platform & Infrastructure** owns the technical recovery work. This team maintains the production environment, manages backups, and leads the restoration of services after a major disruption. They also run regular recovery drills and document the results.

**Routing Core** and **Fleet Insights** are responsible for the availability of their own services. Engineering managers, such as Ines Duarte, ensure that their teams can rebuild a service from source code and configuration if needed.

**Workplace & Operations**, led by Rui Almeida, handles the physical side of a disruption, such as an office closure or a problem with the Berlin or Lisbon workspaces. They also coordinate with building management and local authorities when needed.

**Customer Success** and **Go-to-Market** teams are responsible for communicating with customers during a prolonged disruption. Deniz, a customer success manager in Berlin, and Marek, a field solutions engineer in Poland, are examples of colleagues who would relay status updates to clients in their regions.

**People & Culture**, led by Aylin Demir, supports employees during a disruption. This includes sharing guidance on remote work, checking in on teams, and coordinating with the People Operations specialists such as Lea.

Every employee has a duty to report suspected disruptions promptly. If you notice something unusual, such as a service that will not start, a suspicious email, or an office access problem, contact it-help@kranich.example or security@kranich.example as appropriate.

For a clear assignment of responsibilities in an active incident, refer to the incident response plan in POL-004.

## 4. Questions

If you have questions about this overview, start with your team lead or your local engineering manager. They can help you understand how disaster recovery applies to your daily work.

For questions about data backups, restoration priorities, or recovery testing, contact Platform & Infrastructure through the usual support channel.

For questions about the security aspects of disaster recovery, such as how backups are encrypted or who can access them, contact security@kranich.example.

For questions about your own preparedness, such as what to do if you cannot reach the network from home, or how to request equipment for remote work, contact it-help@kranich.example.

For questions about communication with customers during a disruption, speak with your manager or the Customer Success lead for your region.

For questions about this document itself, including suggestions for improvement, contact Information Security. This overview is reviewed regularly and updated when our systems or our ways of working change. The version history is available in Grove.

Example: Anna, a backend engineer in Lisbon, notices that one of the internal services used for local development is unreachable. She checks whether this is a known issue on the team channel, finds nothing, and reports it to it-help@kranich.example. The Platform & Infrastructure team responds, confirms it is an isolated issue, and resolves it without impact to customers. Anna notes the process for future reference.

Example: Deniz, a customer success manager in Berlin, receives a question from a customer about a brief slowdown in the Kranich Route Cloud. She checks the internal status page, sees that Platform & Infrastructure has already posted an update, and shares the relevant summary with the customer. She does not speculate about the cause or the expected recovery time.

These examples illustrate the everyday side of disaster recovery: staying alert, reporting early, and communicating clearly. The formal procedures and technical details are documented in the policies referenced throughout this overview.

For the complete set of related policies, including backup requirements and business continuity expectations, see POL-004 and any associated documents published by Information Security in Grove.
