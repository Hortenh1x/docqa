---
doc_id: ENG-RFC-02
title: RFC-02: Route planning latency budget
version: "1.0"
effective_date: 2025-02-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-02: Route planning latency budget

## 1. Context

The route-planning endpoint is the most frequently called service in the Kranich Route Cloud. Customer Success and field engineers report that interactive map sessions feel sluggish when plans are recalculated. Users expect to see an updated route within the time it takes them to lift their finger from the mouse.

Today, the endpoint's performance is undefined. Each team in the Routing Core group has its own informal expectations, and Platform & Infrastructure has no basis for prioritizing optimization work. As a result, we sometimes spend effort on algorithmic improvements that do not move the user-visible metric, while ignoring bottlenecks in serialization or network handling.

This RFC proposes a single, measurable latency budget for the route-planning endpoint. The budget applies to the synchronous request–response path only. Batch planning jobs and background recomputation are out of scope.

We deliberately avoid a cascade of sub-budgets for individual components. A single endpoint-level budget gives teams freedom to trade off, for example, solver time against map-matching time, as long as the overall response meets the target.

## 2. Proposal

The route-planning endpoint targets a p95 latency of 370 ms. The p95 is measured end to end at the API gateway, from the moment the gateway accepts the request to the moment it sends the final byte of the response. This includes authentication, request parsing, routing logic, serialization, and network egress inside our infrastructure.

The budget is a target, not a hard cap. We will not reject or queue requests that exceed it. The target is a signal for capacity planning and for performance regression detection in CI.

We define the metric precisely:

- Percentile: p95, computed over a rolling window of one calendar day.
- Scope: all requests to the route-planning endpoint that return a successful response.
- Measurement point: the API gateway, which already records per-request durations.

The target applies to the production environment in the EU region. We will revisit whether separate targets are needed for other regions when we expand deployment.

## 3. Details

The p95 of 370 ms becomes the single source of truth for performance conversations about the route-planning endpoint. Teams should use this number when deciding whether an optimization is worth the complexity it introduces.

We ask each team that touches the request path to consider their contribution to the latency budget. For example, Platform & Infrastructure should keep an eye on gateway overhead and connection pooling. Routing Core should profile solver warm-up and cache hit rates. Fleet Insights should check that any data enrichment called during planning is cached appropriately.

To make the target actionable, we will add a performance regression test to the CI pipeline. The test replays a corpus of recorded production requests against a staging environment. If the p95 of the replayed traffic exceeds the budget, the pipeline fails. The corpus is refreshed quarterly from anonymized production traces.

We also recommend that teams instrument their services with tracing spans that carry the parent request id. This makes it straightforward to find where time is spent when the endpoint misses the budget. We will publish a short runbook on how to read the traces and how to correlate them with gateway logs.

The budget applies to the default tenant configuration. We know that some customers run with unusually large fleets or complex constraints. We will work with Customer Success on a case-by-case basis for those customers, but the default product experience must meet the target.

## 4. Alternatives considered

We considered setting separate budgets for different request types, for example a looser budget for requests that include traffic data or custom constraints. We rejected this because it makes the metric hard to communicate and hard to compare across teams. A single number is easier to remember and easier to test against.

We considered defining the budget at the p99 rather than the p95. The p99 is more sensitive to rare outliers, which are often caused by garbage collection pauses or noisy neighbors on shared infrastructure. Chasing the p99 would push us toward defensive engineering that adds complexity for little user-visible benefit. The p95 reflects the experience of the user who is actively interacting with the map.

We considered measuring latency inside the routing service, excluding gateway and network time. We rejected this because the user experience is what matters, and the gateway is under our control. If the gateway adds meaningful overhead, we want to know about it.

We considered a hard cap with automatic retries or circuit breaking. That approach protects downstream services but does not improve the user experience, because the user still waits for the first attempt to finish or fail. A soft target gives us room to reason about trade-offs without forcing a rigid technical mechanism.

## 5. Rollout

The budget takes effect on the effective date listed in the front matter. From that date, the p95 of 370 ms is the official target for the route-planning endpoint.

In the weeks leading up to the effective date, Platform & Infrastructure will complete two tasks. First, we will verify that the gateway metrics are accurate and that the p95 computation is correct. Second, we will set up the CI regression test with the recorded request corpus.

After the effective date, we will review the measured p95 at the next Platform & Infrastructure review meeting. If the p95 is above the budget, we will open a follow-up work item and assign an owner. If the p95 is comfortably below the budget, we will leave the target as is and revisit it during the next planning cycle.

We will communicate the budget to the Routing Core and Fleet Insights teams through the usual engineering update. We will also add a short note to the relevant service documentation so that new engineers know the target exists.

## 6. Open questions

- Should the budget apply to the route-planning endpoint only, or should we define similar budgets for other interactive endpoints, such as fleet overview or driver assignment?
- How should we handle requests that time out at the client side before the server responds? They are currently excluded from the metric, but they do represent a poor user experience.
- Do we need a separate budget for the route-planning endpoint when it is called from our mobile application, where network conditions are less predictable?
- Who owns the performance regression test corpus, and how often should it be refreshed beyond the quarterly cadence?
- Should the budget be revisited when we introduce a new major version of the routing engine, or should the target remain stable across engine changes?
