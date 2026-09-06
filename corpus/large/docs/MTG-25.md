---
doc_id: MTG-25
title: Meeting Notes — Routing Core weekly (2025-02-22)
effective_date: 2025-02-22
owner: Routing Core weekly
classification: internal
---

# Meeting Notes — Routing Core weekly (2025-02-22)

## 1. Attendees

- Anna (backend engineer, Lisbon)
- Ines Duarte (engineering manager, Berlin)
- Deniz (customer success manager, Berlin, joined for one item)
- Marek (field solutions engineer, joined for one item)

## 2. Discussion

- Anna shared an update on the ongoing work to improve how the routing engine handles multi-stop deliveries with tight time windows. She noted that a few customers in Poland have reported suboptimal sequencing in dense urban areas.
- Marek confirmed this from the field: the issue tends to surface when customers have many stops within a short distance of each other. He offered to share anonymized route examples with the team.
- Ines asked whether the team had considered adjusting the heuristics used for the initial route construction, rather than only the improvement phase. Anna agreed this was worth exploring and would take a look.
- Deniz joined the later part of the call to flag a customer success trend: several clients have asked for a simpler way to visualize why a particular route was chosen. She suggested the team keep this in mind when designing future changes.
- The team briefly discussed the upcoming release cycle and how to sequence the routing work alongside other commitments. No timeline was set; the team agreed to revisit sequencing at the next planning session.
- Anna mentioned she had reviewed the relevant performance documentation and would align her approach with the guidance in POL-004.
- Ines reminded everyone that any changes affecting how routes are priced or presented to customers should be checked against FIN-RATES-2026 before rollout.

## 3. Decisions

- The team will prioritize investigating the urban multi-stop sequencing issue in the next development cycle.
- Anna will prepare a short summary of possible heuristic adjustments for review by the team.
- Marek will share anonymized route examples from Polish customers to help ground the discussion.
- No changes will be made to the routing engine until the team has reviewed Anna’s summary and Marek’s examples.

## 4. Action items

- Anna: prepare a summary of heuristic adjustment options and share with the team.
- Marek: send anonymized route examples to Anna and Ines.
- Ines: schedule a follow-up discussion for the team to review the summary and examples.
- Deniz: circulate the customer feedback about route visualization to the broader team for awareness.
