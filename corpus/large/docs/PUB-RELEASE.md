---
doc_id: PUB-RELEASE
title: Release Notes Policy
version: "1.0"
effective_date: 2025-07-01
owner: Go-to-Market
classification: internal
---

# Release Notes Policy

## 1. Scope

This policy explains how Kranich Software communicates product changes to our customers through release notes. Release notes are the primary way customers learn what is new, what has improved, and what they may need to act on in the Kranich Route Cloud.

This policy applies to all product changes that affect the customer experience, including new features, enhancements, bug fixes, and deprecations. It covers release notes published for the Kranich Route Cloud and its related modules.

Our goal is to be transparent, timely, and helpful. Release notes should let a customer understand the change, why it matters, and whether they need to do anything. We write for a professional logistics audience, avoiding jargon and internal shorthand.

This policy is owned by Go-to-Market. The Product Management teams for Routing Core and Fleet Insights are responsible for drafting content. Platform & Infrastructure supports with technical accuracy. Customer Success reviews notes before publication to confirm they reflect what customers will actually see.

## 2. Cadence

We publish release notes on a regular schedule that aligns with our product delivery cycles. Customers can expect an update whenever a meaningful change ships, rather than waiting for a fixed calendar date.

Release notes appear in the Grove customer portal and are also distributed by email to the customer contacts we have on file. Customer Success may share highlights in account reviews, but the release notes themselves remain the authoritative record.

Each set of release notes follows a consistent structure:

- **Summary** – one or two sentences describing the change in plain language.
- **What changed** – a short description of the behavior before and after the update.
- **Why it matters** – the benefit to the customer’s daily operation.
- **Action required** – only included when the customer must do something, such as updating an integration or confirming a new setting.

We group changes by module. When a change spans more than one module, we note it in each relevant section and link to the primary entry.

Example: Deniz, a customer success manager in Berlin, works with a customer who asks whether a routing improvement affects their nightly batch. Deniz checks the latest release notes and sees the change listed under Routing Core with a note that no action is required. She forwards the entry to the customer, who can plan accordingly.

We aim to publish release notes promptly after a change is available to customers. If a change is rolled out gradually, we publish the notes when the first customers receive it and add a note that availability may vary.

Occasionally we publish an emergency fix that affects only a subset of customers. In that case, we still write release notes, but we may keep them brief and notify affected customers directly through Customer Success.

## 3. Deprecations

A deprecation is a feature or capability that we plan to remove or replace. Because customers build processes around our software, we treat deprecations with particular care.

When we decide to deprecate a feature, we announce it in the release notes before the removal takes effect. The announcement explains:

- What is being deprecated and why.
- What the recommended alternative is, if one exists.
- What customers should do to prepare.

Deprecation announcements are also shared with Customer Success so they can reach out to customers who are known to use the affected feature. We reference the relevant configuration or integration documentation where helpful.

Example: Marek, a field solutions engineer working with clients in Poland, learns from a deprecation notice that a legacy fleet import format will be retired. He reviews which of his clients still use it and contacts them to schedule a migration to the supported format, well before the removal date.

We do not deprecate features without notice. A deprecation appears in at least one set of release notes before the feature is removed. The notes may also refer to related guidance in the product documentation or to FIN-RATES-2026 when the change affects billing or rate configuration.

If a deprecation affects a security control or data-handling practice, we coordinate with Information Security through the process described in POL-004. Customer-facing language in that case is reviewed by Head of Information Security Priya Nayar’s team before publication.

We keep a public history of past deprecations so customers and internal teams can track what has changed over time. When a deprecated feature is finally removed, we publish a short confirmation in the release notes so customers are not surprised by its absence.

Example: Sofia, a product manager for Fleet Insights working remotely from Spain, proposes deprecating an outdated reporting view. She drafts the announcement, checks with Customer Success on which customers use it, and schedules the note for the next release cycle. The note clearly points to the newer dashboard as the recommended alternative.

Release notes are a promise of clarity. When in doubt, we say more rather than less, and we always tell customers where to go for help.
