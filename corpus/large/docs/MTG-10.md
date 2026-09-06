---
doc_id: MTG-10
title: Meeting Notes — Platform sync (2025-11-04)
effective_date: 2025-11-04
owner: Platform sync
classification: internal
---

# Meeting Notes — Platform sync (2025-11-04)

## 1. Attendees

- Jonas (CTO)
- Ines Duarte (engineering manager, Routing Core)
- Anna (backend engineer, Routing Core, Lisbon)
- Sofia (product manager, Fleet Insights)
- Marek (field solutions engineer)
- Deniz (customer success manager)

## 2. Discussion

- Jonas opened with an update on the migration of the routing engine’s deployment pipeline. The team has completed the groundwork and is now testing rollout procedures in staging.
- Anna shared that the Routing Core team has been experiencing intermittent latency when calling the geocoding service. The issue appears only under specific load patterns and is being investigated. No root cause confirmed yet.
- Sofia noted that Fleet Insights customers have begun asking about a new reporting view. She clarified that this is a discovery request, not a committed roadmap item.
- Marek reported feedback from a client in Poland: the batch-import feature works well, but the error messages are not descriptive enough for non-technical users. He suggested improving the wording before the next release.
- Deniz mentioned that several customers have asked whether route changes can be communicated to drivers automatically. Jonas said this is already possible via webhooks, and the Customer Success team should point customers to the API documentation.
- The group briefly discussed the upcoming maintenance window for the platform. Jonas reminded everyone that the window is published on Grove and that any service-impacting changes must be coordinated through Platform & Infrastructure.
- Ines raised a concern about code review turnaround in Routing Core. She proposed setting a shared expectation for reviewers to respond promptly, without inventing a fixed deadline.
- No open security concerns were raised. Priya was not present but has been kept informed via the usual channel.

## 3. Decisions

- The geocoding latency investigation remains with Routing Core; Fleet Insights will not divert engineering time to it.
- The batch-import error message improvements will be scheduled into the next Routing Core iteration, ahead of other non-urgent work.
- Customer Success will refer driver-notification questions to the API documentation rather than creating a custom workaround.
- The team agreed to adopt a shared expectation for timely code review responses, effective immediately, without specifying a numeric target.

## 4. Action items

- Anna: continue investigating the geocoding latency and post findings to the Platform sync channel.
- Ines: coordinate the error message improvements with Anna and assign a reviewer.
- Deniz: share the relevant API documentation link with the Customer Success team.
- Marek: send the exact client feedback and example error text to Ines.
- Sofia: prepare a brief discovery summary on the reporting view and share it with Jonas before the next sync.
- Jonas: confirm the maintenance window details are visible on Grove.
