---
doc_id: ENG-RFC-01
title: RFC-01: Public API rate limiting
version: "1.0"
effective_date: 2025-01-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-01: Public API rate limiting

## 1. Context

Kranich Route Cloud exposes a public API that customers and partners use to push delivery batches, pull route plans, and query fleet telemetry. The API has grown organically since the early product days. Different endpoints were built by different teams at different times, and each team applied its own idea of what a reasonable request volume looks like.

The absence of a uniform rate-limiting policy has created operational friction. A single customer can saturate a shared backend service and degrade the experience for everyone else. Support tickets about throttling behaviour are inconsistent — some customers report being cut off abruptly, while others never hit a limit and unknowingly drive up our infrastructure cost. Our internal monitoring shows that a small number of API keys generate a disproportionate share of traffic, and that traffic patterns are spiky rather than steady.

Platform & Infrastructure owns the API gateway. We want a single, well-documented rate-limiting scheme that applies to every public endpoint, is easy for customers to understand, and is straightforward for our own engineers to implement and maintain.

## 2. Proposal

We propose a token-bucket rate limiter enforced at the API gateway for all public endpoints. The limiter will be applied per API key, not per IP address. This keeps the behaviour predictable for customers who call from multiple servers or through rotating egress IPs.

The rate limit will be a fixed ceiling for every API key, regardless of plan tier. We deliberately avoid tiered limits for now — see §4 for why. The ceiling is set at a value that accommodates the vast majority of legitimate integration patterns we see today, while still protecting shared infrastructure from pathological traffic.

When a client exceeds the limit, the gateway will return a standard HTTP response indicating that the client has been throttled. The response will include headers that tell the client how many requests remain in the current window and when the bucket will refill. Clients that respect these headers can self-throttle gracefully.

We also propose that the limiter applies to all HTTP methods equally — GET, POST, PUT, PATCH and DELETE all consume from the same bucket. This simplifies the mental model for customers and prevents a loophole where a client shifts load from one method to another to bypass the limit.

## 3. Details

The public API is limited to 700 requests per minute per API key. The counter is a token bucket that refills continuously, so a client that stays under the ceiling never notices the limiter. A client that bursts above the ceiling will be throttled until the bucket has refilled enough tokens to allow the next request.

The limit is enforced at the gateway layer, before requests reach any application service. This means the limiter protects Routing Core, Fleet Insights and every downstream dependency uniformly. Endpoints that are internal-only — for example, the service-to-service calls between our microservices — are not subject to the public API rate limit.

The gateway will include the following headers in every API response:

- A header indicating the total number of requests permitted in the window.
- A header indicating the number of requests remaining in the current window.
- A header indicating the Unix timestamp at which the window resets.

When a client exceeds the limit, the gateway responds with a status code in the client-error range that unambiguously signals throttling. The response body will be a short JSON message explaining that the rate limit was exceeded and pointing to the documentation.

The limiter configuration lives in the gateway’s deployment manifest. Changing the limit requires a code review and a merge to the main branch, followed by a standard deployment. We will not expose a self-service knob for changing limits per customer in this iteration.

Example: Anna, a backend engineer in Lisbon, integrates a customer’s warehouse system with our API. The customer’s warehouse pushes a batch of deliveries every few minutes, which amounts to well under the ceiling. Anna verifies the response headers during development and confirms that the integration never approaches the limit.

## 4. Alternatives considered

We considered a per-IP limiter instead of per-API-key. This was rejected because many of our customers call from cloud providers with shared egress IP ranges. A per-IP limit would punish legitimate customers who happen to share an IP with a noisy neighbour, and it would be trivially bypassed by rotating IPs.

We considered tiered limits, where higher-paying plans receive a higher ceiling. This was rejected for the current iteration because it adds complexity to the gateway, to the billing system and to our documentation. We can revisit tiering later if sales feedback shows that customers want to buy more headroom.

We considered a sliding-window counter instead of a token bucket. The sliding window is simpler to reason about, but it produces hard cut-offs at window boundaries. The token bucket smooths out bursts, which better matches how our customers actually integrate — they often sync in short bursts after a period of quiet.

We considered making the limit configurable per customer through the admin UI. This was rejected because it pushes operational burden onto Customer Success and invites special-case negotiations. A uniform, published limit is easier to defend and easier to enforce.

We considered not rate-limiting at all and instead relying on horizontal autoscaling. This was rejected on cost grounds and on fairness grounds — autoscaling protects us from downtime but does not protect one customer from another’s noisy neighbour behaviour.

## 5. Rollout

We will roll out the rate limiter in stages so that customers are not surprised.

First, we enable the limiter in a shadow mode. The gateway will evaluate the token bucket and log whether a request would have been throttled, but it will not actually block any traffic. We will run shadow mode for a few weeks and compare the would-be-throttled requests against our monitoring baseline.

Second, we enable the limiter for a small set of internal test API keys that our own engineering teams use. This validates the implementation in a live environment without affecting external customers.

Third, we enable the limiter for all API keys, but with a generous initial ceiling. We will monitor throttling events closely for the first few days. If a legitimate customer hits the ceiling, Customer Success will work with them to understand their traffic pattern, and we will consider whether the ceiling needs adjustment before the policy becomes permanent.

We will publish a changelog entry and a short documentation update on the same day the limiter goes live for all customers. The documentation will explain the limit, the response headers, and the recommended backoff strategy for clients that receive a throttling response.

## 6. Open questions

- Should the rate limit apply to the webhook delivery endpoints that push events to our customers, or only to the request endpoints that customers call against us? Webhooks are outbound traffic and may warrant a separate policy.
- Should batch endpoints — for example, uploading many deliveries in a single call — count as one request or as multiple requests based on the payload size? We currently assume one request per HTTP call, but product may want to differentiate.
- Do we need a mechanism for temporary emergency overrides, for example when a customer runs a one-off migration? If so, who approves the override and how is it audited?
- How do we communicate limit changes to customers who are already integrated and may not read the changelog? We may need an email notification or an in-product banner.
- Should the limiter account for authentication failures? A client that sends invalid credentials currently consumes no meaningful backend resources, but a flood of bad requests could still be worth throttling.
