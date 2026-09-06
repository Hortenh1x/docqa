---
doc_id: ENG-GUIDE-RELEASE
title: Release Process
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# Release Process

## 1. Purpose

This guide describes how Kranich Route Cloud releases are planned, executed, and, if needed, undone. It is written for engineers, product managers, and customer-facing teams who need to know what happens when code ships.

A release is more than merging to main. It is a coordinated event that involves Routing Core, Fleet Insights, Platform & Infrastructure, and Customer Success. This guide sets expectations so everyone can work together calmly and predictably.

We aim for releases that are boring. If a release is boring, it means the preparation was thorough, the rollout was smooth, and customers noticed nothing except improvements.

## 2. Cadence

Kranich Route Cloud follows a regular release cadence. Platform & Infrastructure owns the schedule and communicates it through the engineering calendar and Grove.

Most releases are incremental and small. We prefer shipping frequently over batching many changes into one large release. Small releases are easier to review, easier to test, and easier to roll back if something goes wrong.

Each release goes through the same stages:

- Code review and automated checks
- Staging deployment and verification
- Production deployment, phased by customer cohort
- Post-release monitoring

The release coordinator for the week is named in the team channel. That person is the single point of contact for release-related questions and decisions. If you are unsure whether your change belongs in an upcoming release, ask the release coordinator.

Feature flags are the default mechanism for controlling exposure. If a feature is not ready for all customers, it ships behind a flag. This keeps the release cadence steady even when individual features are still maturing.

## 3. Freeze windows

A release freeze starts 2 days before a major customer go-live. The freeze applies to all production changes, including configuration changes and database migrations, unless the change is explicitly approved as an exception by Platform & Infrastructure.

The purpose of a freeze is stability. When a major customer goes live, the last thing we want is an unrelated deployment introducing risk. The freeze gives the customer team and the engineering teams a quiet window to focus.

During a freeze, you may still merge code to main, but you must not deploy it to production. You may also run read-only operations and prepare changes that are scheduled to go out after the freeze lifts.

The freeze lifts once the go-live is verified and the release coordinator announces the end of the freeze in the team channel. If the go-live is delayed, the freeze extends automatically until the new go-live date is confirmed.

Example: Deniz, a customer success manager in Berlin, coordinates a go-live for a logistics operator in Poland. She confirms the go-live date with Marek, the field solutions engineer. Platform & Infrastructure announces the freeze. Anna, a backend engineer in Lisbon, has a performance improvement ready, but she waits until the freeze lifts before deploying it.

## 4. Rollback

Every release must have a rollback plan. The rollback plan is part of the release notes and is reviewed by the release coordinator before deployment begins.

Rollback means returning the production environment to the previous known-good state. For most releases, this is done by redeploying the previous artifact. For releases that include database migrations, the rollback plan must state explicitly whether the migration is reversible and what the reversal steps are.

If a release causes a customer-facing incident, the default decision is to roll back first and investigate later. Speed matters. Do not spend time trying to fix forward if a rollback restores service promptly.

The rollback decision is made by the release coordinator, in consultation with the on-call engineer and the engineering manager of the affected team. If the incident involves a major customer, the release coordinator informs the Head of Workplace & Operations, Rui Almeida, who coordinates with Customer Success.

After a rollback, the team holds a brief review to understand what happened and what should change before the next attempt. The review is blameless. We are looking for process improvements, not individuals at fault.

Example: Sofia, a product manager in Fleet Insights, ships a new reporting view. Shortly after deployment, Customer Success reports that a customer sees incorrect totals. The release coordinator decides to roll back. The previous version is restored within minutes. The team later finds that the issue was a data transformation error, fixes it, and ships the view again in the next release.

## 5. Questions

If you have questions about the release process, start by asking in the engineering channel or your team channel. The release coordinator for the current week is the best first point of contact.

For questions about a specific release, including freeze windows and rollback plans, contact the release coordinator directly. For broader process feedback, reach out to the Head of Information Security, Priya Nayar, or the CTO, Jonas Weber.

If you notice that this guide is out of date, suggest an update through Grove. The owner of this document is Platform & Infrastructure, and they review it regularly alongside related policies such as POL-004.

For questions about how releases interact with customer contracts or rate changes, refer to FIN-RATES-2026 and speak with your manager or the finance team.
