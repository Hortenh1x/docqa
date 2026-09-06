---
doc_id: ENG-GUIDE-OBSERV
title: Observability Guide
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# Observability Guide

## 1. Purpose

This guide explains how we practice observability at Kranich Software GmbH. Observability helps us understand what our systems are doing, why they behave the way they do, and what we can improve. It is a shared responsibility across all engineering teams, not just Platform & Infrastructure.

We aim for a culture where every engineer can inspect the health of the services they build and operate. When something goes wrong, the right signals should be easy to find. When something goes well, we should be able to learn from that too.

Our observability practice rests on three pillars: metrics, tracing, and dashboards. Each pillar serves a distinct purpose, and together they give us a complete picture of the Kranich Route Cloud.

## 2. Metrics

Metrics are numeric measurements collected over time. They tell us about the state of our services, such as request rates, error rates, and resource usage. Metrics are best for alerting and for spotting trends.

Every service in the Kranich Route Cloud must expose a set of standard metrics. These include request counts, error counts, and latency distributions. Services that handle background work should also expose queue depths and processing outcomes.

We use a common naming convention for metrics across all teams. This makes it possible to compare services and to build shared dashboards. The convention is documented in the internal engineering wiki.

Metrics are collected centrally by Platform & Infrastructure. Teams do not run their own metric stores. If you need a new metric, add it to the service's instrumentation and follow the naming convention.

Example: Anna, a backend engineer in Lisbon, adds a metric to track how often a routing job is retried. She follows the naming convention so that the metric appears automatically on the team's dashboard.

## 3. Tracing

Tracing follows a single request as it moves through multiple services. The Kranich Route Cloud is a distributed system, and a single user action can touch several components. Tracing helps us see where time is spent and where failures occur.

Every service must propagate trace context. This means that when a service calls another service, it passes along the trace identifier. We use the standard trace context format so that traces are continuous across service boundaries.

Traces are sampled. We do not store every trace, as that would be impractical. The sampling rate is managed centrally, and teams can request a higher rate for specific services during investigations.

When you are debugging a slow request or an error, start with the trace. The trace shows you the path the request took and the duration of each step. This often reveals the root cause faster than looking at logs.

Example: Deniz, a customer success manager in Berlin, reports that a client's route upload is slow. Marek, a field solutions engineer, opens the trace for that upload and sees that the delay comes from a third-party geocoding service. He shares the trace with the Routing Core team.

## 4. Dashboards

Dashboards turn metrics and traces into a visual overview. They help us monitor services at a glance and during incidents. Dashboards are not just for on-call engineers; they are for anyone who wants to understand a service.

Each team maintains dashboards for its own services. Platform & Infrastructure maintains a set of global dashboards that cover the overall health of the Kranich Route Cloud. These global dashboards show the status of critical user journeys, such as route optimization runs and fleet data ingestion.

A good dashboard tells a story. It starts with the user experience, then drills into service health, and finally shows infrastructure details. Avoid dashboards that are cluttered with too many panels. If a dashboard requires a manual to understand, it needs to be simplified.

Dashboards should be reviewed regularly. When a service changes significantly, its dashboard should change too. Outdated dashboards are worse than no dashboard because they mislead.

Example: Sofia, a product manager in Fleet Insights, wants to understand how often fleet tracking data arrives late. She looks at the Fleet Insights dashboard, which shows a clear view of data freshness across all connected fleets.

## 5. Questions

This section answers common questions about our observability practice.

**Who is responsible for observability?**

Every engineer is responsible for the observability of the services they build. Platform & Infrastructure provides the tooling and the standards. If you see a gap in coverage, raise it with your team or with Platform & Infrastructure.

**Where do I find the dashboards for my team?**

The central dashboard list is on the Grove intranet. Each team's dashboards are linked from the team page. If you cannot find what you need, ask your engineering manager.

**How do I get access to tracing tools?**

Access is granted through the standard request process. Put in a request to Platform & Infrastructure, and you will receive access promptly. Access levels follow the principle of least privilege.

**What should I do if a metric or trace is missing?**

Check the naming convention first. If the metric or trace follows the convention but does not appear, contact Platform & Infrastructure. If the signal is genuinely missing from your service, add it as part of your regular development work.

**How do we handle observability during an incident?**

During an incident, the on-call engineer leads the investigation. They use dashboards and traces to understand the impact and the cause. After the incident, the team writes a review that includes what observability gaps were found and how they will be closed.

**Can I build my own dashboard?**

Yes. Anyone can create a personal dashboard for their own use. If you build a dashboard that would help your whole team, publish it to the team dashboard list. Remember to follow the dashboard guidelines in §4.

**What about customer data in observability tools?**

Observability data may contain technical identifiers but must not contain customer content or personal data. If you need to inspect a specific customer's behavior, use the approved debugging procedures and involve Customer Success. See the security policy for details.

If you have further questions, reach out to Platform & Infrastructure or check the engineering wiki. Observability is a practice we grow together, and your feedback helps us improve.
