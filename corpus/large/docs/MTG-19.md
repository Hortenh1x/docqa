---
doc_id: MTG-19
title: Meeting Notes — Release planning (2025-08-04)
effective_date: 2025-08-04
owner: Release planning
classification: internal
---

# Meeting Notes — Release planning (2025-08-04)

## 1. Attendees

- Marta (CEO)
- Jonas (CTO)
- Anna (Routing Core, Lisbon)
- Sofia (Fleet Insights, remote from Spain)
- Deniz (Customer Success, Berlin)
- Marek (field solutions engineer, Poland)
- Ines Duarte (engineering manager, Routing Core, Berlin)

## 2. Discussion

- Jonas opened the session by recapping the goals for the upcoming release cycle. The main focus is on stability for Routing Core and on surfacing richer insights for Fleet Insights customers.
- Anna walked through the current state of the routing engine. The team has addressed several edge cases reported by customers in recent months, and the remaining work is mostly around regression testing. She noted that the team would like to run an extended beta with a small group of clients before the general rollout.
- Sofia shared the Fleet Insights roadmap. The team is preparing a new dashboard view that helps dispatchers compare planned versus actual routes. She asked for input from Customer Success on how to frame the feature in user-facing messaging.
- Deniz reported that customers are generally positive about recent improvements, but some have asked for clearer communication when a planned route changes mid-day. This sparked a discussion about notification preferences and whether the platform should let customers choose the channel.
- Marek mentioned that several Polish clients are interested in better support for multi-stop deliveries with tight time windows. He offered to coordinate a feedback session with a few of those clients to validate assumptions.
- Ines raised a concern about the release timeline. She feels the team needs a few extra days for quality assurance, especially around the integration between Routing Core and Fleet Insights. Jonas agreed that quality should not be rushed.
- The group briefly touched on internal tooling. Rui had shared a note about desk availability at the Berlin office, but the team agreed this was not relevant for release planning.
- No figures, dates beyond the current year, or numeric targets were discussed. The group will rely on qualitative milestones and the existing tracking documents.

## 3. Decisions

- The release will be split into two phases: first a beta with selected customers, then the general rollout. The beta group will be chosen jointly by Customer Success and the engineering teams.
- Fleet Insights will include the new dashboard view in the same release cycle, provided the integration testing passes.
- Customer Success will prepare a short communication template for route-change notifications, to be reviewed by Sofia before release.
- Marek will organize a feedback session with Polish clients, but only after the beta scope is confirmed.
- The team will not commit to a fixed date for the general rollout until the beta results are reviewed.

## 4. Action items

- Anna: prepare a beta candidate build and share it with Jonas and Ines for review.
- Sofia: finalize the dashboard specification and share it with Deniz for feedback.
- Deniz: draft the communication template for route-change notifications.
- Marek: reach out to a few Polish clients to gauge interest in a feedback session.
- Jonas: coordinate the beta selection criteria with Deniz and Ines.
- Ines: update the release tracking document with the two-phase approach.
