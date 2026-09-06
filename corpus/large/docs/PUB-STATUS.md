---
doc_id: PUB-STATUS
title: Status Page Guide
version: "1.0"
effective_date: 2025-07-01
owner: Go-to-Market
classification: internal
---

# Status Page Guide

## 1. Scope

This guide explains how Kranich Route Cloud's public status page works, what it shows, and how you can stay informed about the health of our services. The status page is our primary channel for communicating service availability and incidents to customers, prospects, and partners.

If you are a Kranich employee, this guide also helps you understand what customers see, so you can answer questions confidently. For internal incident response procedures, refer to the relevant security and operations policies instead.

The status page is managed by the Go-to-Market team, with input from Platform & Infrastructure. All content published there is customer-facing. Keep that in mind when you describe issues: write in plain language, avoid jargon, and never include internal details such as employee names or root-cause speculation.

## 2. Components

The status page covers the main components of the Kranich Route Cloud platform:

- **Routing Core** — the engine that calculates optimized routes and schedules.
- **Fleet Insights** — reporting and analytics features.
- **Platform & Infrastructure** — authentication, API access, and underlying infrastructure.
- **Customer Portal** — the web interface customers use to manage their account and settings.

Each component shows one of the following states:

- **Operational** — the component is working as expected.
- **Degraded performance** — the component is available but slower or less reliable than usual.
- **Partial outage** — some customers or features are affected.
- **Major outage** — the component is unavailable or severely impaired.

When a component is not fully operational, the status page shows a brief description of the issue and, when possible, an estimated time of resolution. We update this description as the situation evolves. After the issue is resolved, the component returns to *Operational* and a summary of the incident remains visible on the page for a while.

The status page also displays planned maintenance windows in advance. We schedule maintenance during low-usage periods whenever possible. If a component will be unavailable during maintenance, we mark it accordingly so customers are not surprised.

Example: Deniz, a customer success manager in Berlin, receives a question from a customer about a slow-loading report. Deniz checks the status page, sees that Fleet Insights is marked as *Degraded performance*, and reassures the customer that the team is aware and working on it.

## 3. Subscribing

Anyone can view the status page without an account. To receive updates automatically, visitors can subscribe to notifications. Subscriptions are available by email and through a webhook for customers who prefer to integrate alerts into their own monitoring tools.

Subscribers choose which components they want to follow. For example, a customer who only uses Routing Core may subscribe to that component alone and skip notifications about Fleet Insights. Subscribers can change their preferences or unsubscribe at any time, directly from the status page.

Notification types include:

- **Incident created** — when a component leaves the *Operational* state.
- **Incident updated** — when the status or description changes.
- **Incident resolved** — when the component returns to *Operational*.
- **Maintenance scheduled** — announced before planned work begins.

We send notifications promptly whenever a status changes. There is no need to refresh the page repeatedly; once you subscribe, updates arrive automatically.

Example: Marek, a field solutions engineer working with clients in Poland, subscribes to notifications for Routing Core and Platform & Infrastructure. When a major outage occurs during a client rollout, Marek receives the alert right away and can inform the client before they notice any issue.

### Tips for employees

- Bookmark the status page and check it before you contact customers about known issues.
- If a customer reports a problem, check the status page first. If an incident is already listed, refer the customer to the page for updates.
- Never promise a resolution time that is not published on the status page.
- If you believe an incident is missing or inaccurate, contact Platform & Infrastructure through the usual internal channels, not through the status page itself.

The status page is a small but important part of how we build trust with our customers. Keeping it accurate and up to date helps everyone — customers, prospects, and our own teams — work with confidence.
