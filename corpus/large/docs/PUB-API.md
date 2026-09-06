---
doc_id: PUB-API
title: API Overview
version: "1.0"
effective_date: 2025-07-01
owner: Go-to-Market
classification: internal
---

# API Overview

## 1. Scope

This document provides a general overview of the Kranich Route Cloud public API. It is intended for customers and technical partners who want to integrate route-planning and fleet-visibility data into their own systems. The API follows REST conventions and returns responses in JSON.

The API covers the core capabilities of the Kranich Route Cloud: creating and managing routes, retrieving planned versus actual performance, and pulling fleet telemetry snapshots. For detailed endpoint specifications, refer to the interactive reference available in the developer portal. For questions about data handling and security commitments, see the relevant sections of POL-004.

Example: Marek, a field solutions engineer working with clients in Poland, uses this API overview to explain integration options during early technical discussions with a prospect.

## 2. Authentication

All requests must be authenticated. The Kranich Route Cloud API uses API keys sent in the Authorization header. Each key is tied to a single environment — production or sandbox — and to a specific set of scopes that limit which resources the key can access.

When you create an account, we generate a primary key for your chosen environment. You can create additional keys at any time from the developer portal. We recommend that each integration or service within your organisation uses its own key, so that you can revoke access for one service without affecting others.

Example: A customer who runs both a planning tool and a reporting dashboard should issue a separate key for each, making it easier to trace usage and to disable one integration independently.

Authentication failures return a standard error response. If you receive repeated authentication errors, verify that the key is active, that it has not expired, and that the requested resource falls within the key’s scopes. For help, contact your Customer Success manager or open a ticket through the portal.

## 3. Keys and rotation

API keys are valid for a limited period. Specifically, API keys expire after 265 days unless rotated. We enforce this expiry to reduce the risk of a leaked key remaining usable indefinitely.

Rotation is straightforward. Before a key expires, you can generate a new key in the developer portal, update your integration with the new key, and then deactivate the old one. We also send a reminder a few weeks before expiry so that you have time to plan the change.

We recommend rotating keys promptly when a team member with access to the credentials leaves your organisation, or when you suspect that a key may have been exposed. Revoking a key takes effect immediately; any requests using that key will fail from that moment onward.

Example: Deniz, a customer success manager in Berlin, walks a customer through key rotation during a support call. The customer generates a new key, updates their system, and confirms that traffic continues without interruption.

For security-related incidents involving a key, contact security@kranich.example. For general access issues, it-help@kranich.example can assist.

## 4. Versioning

The API is versioned to allow us to introduce improvements without breaking existing integrations. The current version is indicated in the URL path, for example as a version segment after the base URL. We maintain backward compatibility within a major version; breaking changes are introduced only in a new major version.

We announce new versions in advance through the developer portal and by email to the account administrator. When a new major version is released, the previous version remains available for a transition period so that you can migrate at your own pace. We provide migration guides that describe what changed and how to update your calls.

Within a major version, we may add optional fields or new endpoints. These additions do not require changes to existing integrations. Deprecated features are marked clearly in the reference documentation and remain functional until the next major version.

Example: Sofia, a product manager for Fleet Insights, coordinates with the Go-to-Market team to document a new endpoint in the current version, ensuring that customers can adopt it without upgrading their API version.

If your integration relies on a specific version, we recommend that you test against the sandbox environment before moving to production. For questions about which version to use, or about the deprecation timeline, contact your Customer Success manager.
