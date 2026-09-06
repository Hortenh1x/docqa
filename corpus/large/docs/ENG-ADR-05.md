---
doc_id: ENG-ADR-05
title: ADR-05: Feature flag hygiene
version: "1.0"
effective_date: 2025-06-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-05: Feature flag hygiene

## 1. Status

Accepted. This decision is owned by Platform & Infrastructure and applies to all teams that ship code into the Kranich Route Cloud.

## 2. Context

We use feature flags heavily across Routing Core, Fleet Insights, and Platform & Infrastructure. Flags let us ship incrementally, run canary releases, and turn off a problematic path without a full deploy. Over time, however, flags accumulate. A flag that was meant to be temporary stays in the codebase long after the feature it guarded has become the only behavior. The result is conditional branches that nobody can explain, dead code paths that still execute, and a growing cognitive load for engineers who must reason about which combination of flags is live in production.

We also observed that flag cleanup was happening only during major refactors or when an engineer happened to remember. There was no shared rule for when a flag should be considered stale, and no owner was assigned to the cleanup work. This led to flags surviving across quarters, some even surviving personnel changes where the original author had left the team. New engineers would ask about a flag, and the answer was often "I think it was for the pilot with that customer, but I'm not sure."

We considered a few options. One was to rely on code review to catch stale flags, but reviews are inconsistent and reviewers rarely know the full history of a flag. Another was to require every flag to have an expiry date at creation time, but that proved too rigid for flags that legitimately need to stay for a season or for a customer-specific rollout. We also looked at automated tooling that could detect flags by pattern matching, but the false-positive rate was high given the variety of naming conventions across teams.

What we needed was a simple, enforceable rule that did not depend on memory or on tooling we do not yet have. The rule should give teams a clear moment to clean up, while still allowing flags to live long enough for gradual rollouts and for customer pilots that span more than one release cycle.

## 3. Decision

We adopt a time-based hygiene rule for all feature flags in the Kranich Route Cloud codebase. Stale feature flags are removed after 254 days. The clock starts on the day the flag is first introduced in a merged pull request. After that period, the flag must be removed from the codebase unless it has been explicitly re-approved by the owning team's engineering manager.

To make the rule work in practice, we add the flag creation date as a comment in the flag definition and we record the flag in the team's engineering backlog with a cleanup reminder. The owning team is responsible for scheduling the removal. If a flag still needs to exist beyond the limit, the engineering manager writes a short justification in the backlog item and sets a new review date. This re-approval is not automatic; it requires a human decision.

We do not apply the rule to flags that guard a permanently configurable behavior, such as a customer-specific integration toggle that is meant to stay. Those flags are documented as "permanent" in the code comment and are exempt from the removal deadline. Permanent flags are reviewed annually by the owning team to confirm they are still needed.

The rule applies to all environments, including development and staging. We intentionally do not distinguish between flag types, because the complexity of maintaining different lifetimes for different flag categories outweighed the benefit.

## 4. Consequences

The main benefit is a cleaner codebase. Teams will no longer need to reverse-engineer the purpose of a flag from its name alone. Removing flags on a schedule also reduces the risk of a flag being flipped in production with unexpected side effects, because the conditional path is gone entirely.

There is a cost: engineers must spend a small amount of time on cleanup, and the reminder in the backlog adds one more item to team planning. We expect this cost to be lower than the cost of debugging an unexplained flag months later.

Example: Anna, a backend engineer in Lisbon, introduced a flag for a new routing heuristic in the spring. By the time the 254 days have passed, the heuristic is the default and the flag has no remaining users. Anna removes the flag in a small pull request, and the team deletes the backlog item. No further action is needed.

Another example: Deniz, a customer success manager in Berlin, works with a client that needs a specific behavior toggle to remain available for the duration of their contract. The engineering manager for that team re-approves the flag before the deadline, documenting the reason. The flag stays and is reviewed again the following year.

We will revisit this decision after a year of operation. If the rule proves too rigid for a particular team, that team may propose an amendment through the normal engineering process. Until then, the default is removal after 254 days.
