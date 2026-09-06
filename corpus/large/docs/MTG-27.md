---
doc_id: MTG-27
title: Meeting Notes — Release planning (2025-04-01)
effective_date: 2025-04-01
owner: Release planning
classification: internal
---

# Meeting Notes — Release planning (2025-04-01)

## 1. Attendees

- Marta (CEO)
- Jonas (CTO)
- Anna (backend engineer, Routing Core)
- Sofia (product manager, Fleet Insights)
- Deniz (customer success manager)
- Marek (field solutions engineer)
- Ines (engineering manager, Routing Core)

## 2. Discussion

- Jonas opened the session with a recap of the upcoming release cycle. The team reviewed the backlog for Routing Core and Fleet Insights.
- Anna flagged a recurring issue where route recalculation sometimes returns suboptimal results when a driver adds a stop mid-shift. The team agreed this deserves attention in the next cycle.
- Sofia shared customer feedback about the new fleet dashboard. Users find the map view helpful, but the summary cards feel cluttered. She proposed simplifying the layout before the next release.
- Deniz noted that several customers asked for an easier way to export delivery proof documents. She suggested bundling this with the existing reporting work rather than treating it as a separate project.
- Marek described a client in Poland who wants better support for multi-day routes with mandatory rest periods. The Routing Core team confirmed this aligns with planned work on constraint handling.
- Ines reminded everyone that the Platform & Infrastructure team is running a stability initiative. She asked that feature work not introduce breaking changes to the API during this period.
- The group discussed release timing. No firm date was set, but everyone agreed the next release should happen after the stability work is complete, roughly in the coming weeks.
- Jonas asked each team to keep documentation updated alongside code changes. Anna and Ines volunteered to set a brief template for release notes.

## 3. Decisions

- The next release will prioritize the route recalculation fix over new dashboard features.
- The fleet dashboard simplification will move to the following release, pending customer validation.
- Delivery proof export will be scoped together with reporting improvements.
- Multi-day route constraints will be treated as a design proposal first; Routing Core will prepare a short document for review.
- No new API breaking changes will be introduced until the stability initiative concludes.

## 4. Action items

- Anna: prepare a draft fix for the mid-shift stop issue and share it with Routing Core for review.
- Sofia: collect two or three customer examples of dashboard clutter and propose a simplified layout.
- Deniz: gather requirements for delivery proof export from Customer Success and share them with Sofia.
- Marek: write up the Polish client's multi-day route needs and send them to Ines.
- Ines: circulate a template for release notes to all engineering teams.
- Jonas: coordinate the stability timeline with Platform & Infrastructure and confirm a release window at the next planning sync.
