---
doc_id: MTG-29
title: Meeting Notes — Fleet Insights planning (2025-06-07)
effective_date: 2025-06-07
owner: Fleet Insights planning
classification: internal
---

# Meeting Notes — Fleet Insights planning (2025-06-07)

## 1. Attendees

- Sofia (product manager, Fleet Insights, remote from Spain)
- Anna (backend engineer, Routing Core, Lisbon)
- Deniz (customer success manager, Berlin)
- Marek (field solutions engineer, Poland)
- Jonas (CTO)
- Ines Duarte (engineering manager, Routing Core, Berlin)

## 2. Discussion

- Sofia opened with a recap of the Fleet Insights roadmap. The team reviewed upcoming work tied to FIN-RATES-2026 and discussed how those changes interact with the Routing Core platform.
- Anna noted that the Routing Core team has capacity to support Fleet Insights on a shared data pipeline. She suggested aligning on a common schema early to avoid rework later.
- Deniz shared feedback from recent customer conversations. Several mid-size logistics operators are asking for clearer visibility into driver behavior and fuel efficiency. She emphasised that customers value simple dashboards over dense reports.
- Marek added that clients in Poland are particularly interested in predictive maintenance alerts. He recommended involving a field perspective during the design phase, not only after a prototype exists.
- Jonas asked the group to consider how Fleet Insights can reuse existing components from the Routing Core rather than building from scratch. He pointed to POL-004 as a reference for how cross-team work should be governed.
- The group discussed timing. Everyone agreed that the next milestone should be driven by customer readiness, not by an arbitrary calendar date. Sofia proposed a phased rollout, starting with a small group of design partners.
- Ines reminded the team that engineering capacity is shared. She asked for early visibility into any cross-team dependency so managers can plan accordingly.
- The conversation touched on documentation. The group agreed that notes and decisions should live in Grove so that colleagues in the Lisbon and Berlin offices can find them easily.

## 3. Decisions

- Fleet Insights will adopt a phased rollout approach, beginning with a limited set of design partners.
- Anna and Ines will coordinate a short technical alignment between Routing Core and Fleet Insights before detailed planning continues.
- Deniz will compile a short list of customer scenarios to guide the dashboard design. Marek will contribute the field perspective from Poland.
- All planning artifacts will be stored in Grove, with a pointer from the Fleet Insights channel.

## 4. Action items

- Sofia to draft a short product brief and share it with the group for review.
- Anna to schedule a technical alignment session with Ines and the relevant engineers.
- Deniz to gather customer feedback notes and share them with Sofia.
- Marek to document the predictive maintenance use cases from Poland and send them to the group.
- Jonas to confirm whether any procurement steps are needed for the shared data tooling, referencing POL-004 if applicable.
