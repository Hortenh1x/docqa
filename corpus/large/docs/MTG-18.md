---
doc_id: MTG-18
title: Meeting Notes — Platform sync (2025-07-01)
effective_date: 2025-07-01
owner: Platform sync
classification: internal
---

# Meeting Notes — Platform sync (2025-07-01)

## 1. Attendees

- Jonas (CTO)
- Ines Duarte (Routing Core)
- Anna (Routing Core, Lisbon)
- Sofia (Fleet Insights)
- Priya (Information Security)
- Rui (Workplace & Operations)
- Deniz (Customer Success)

## 2. Discussion

- Jonas opened with a quick status round. Anna reported that the Routing Core team has wrapped up the latest batch of improvements to the route-calculation engine and is now looking at how to handle a growing list of edge cases reported by customers.
- Ines added that the team is keen to get more visibility into how the engine behaves under unusual load, and asked whether Platform & Infrastructure could help with load testing.
- Sofia shared that Fleet Insights is planning a release that will surface driver availability more prominently. She flagged a potential dependency on the routing engine’s data model.
- Priya reminded everyone that any new data sharing between the routing engine and Fleet Insights needs a quick privacy review. She offered to set up a short session with the relevant engineers.
- Deniz mentioned that several customers have asked for a clearer way to see why a route was chosen. She suggested that better explanations in the UI would reduce support tickets.
- Rui noted that the Lisbon office has a few spare desks and monitors that could be shipped to colleagues who need them, but he said there is no rush.
- The group briefly discussed the upcoming maintenance window. Priya confirmed that the security team has no concerns with the proposed timing, as long as the change is well documented.

## 3. Decisions

- The routing engine and Fleet Insights will coordinate on the data-model change through a shared design note, with Priya reviewing it before implementation.
- The team will add a lightweight explanation feature to the route view, scoped to the most common customer questions first.
- Load testing will be scheduled outside of peak customer hours, with Platform & Infrastructure coordinating the environment.
- No new cross-team dependencies will be introduced without a short written summary shared on the platform channel.

## 4. Action items

- Anna to draft the shared design note for the data-model change and send it to Priya for review.
- Sofia to share the Fleet Insights release timeline with the Routing Core team so they can plan around it.
- Deniz to collect a few examples of the most common route-explanation questions from customers and post them on the platform channel.
- Rui to check with anyone who needs additional equipment and arrange shipping from the Lisbon office.
- Jonas to confirm the maintenance window details with Platform & Infrastructure and share the final plan with all teams.
