---
doc_id: MTG-06
title: Meeting Notes — Security council (2025-07-19)
effective_date: 2025-07-19
owner: Security council
classification: internal
---

# Meeting Notes — Security council (2025-07-19)

## 1. Attendees

Priya (chair), Jonas, Marta, Aylin, Rui, and Anna joined remotely from Lisbon. Deniz and Marek sent apologies. Sofia attended for part of the session to share the Fleet Insights perspective.

## 2. Discussion

- Priya opened with a review of the current threat landscape, noting an uptick in phishing attempts targeting logistics operators. She referenced findings from POL-004 and reminded everyone that reporting suspicious emails to security@kranich.example remains the first line of defense.
- The council discussed the upcoming rollout of a new access-control feature for the Kranich Route Cloud. Anna raised a concern about the deployment schedule overlapping with peak client usage in Poland. The group agreed to review the window carefully.
- Jonas summarized a recent penetration test. No critical findings emerged, but a few medium-priority items were logged. He will share the full report with the Platform & Infrastructure team.
- Aylin asked about onboarding practices for new joiners, specifically around security training. Priya confirmed that the current program covers password hygiene and 1Password usage, and that refresher material is available on Grove.
- Rui noted that the Lisbon office will host a small security awareness session next month. He asked for a short presentation from Priya, which she agreed to prepare.
- The council briefly touched on vendor risk. Marek had flagged a client request that involved a third-party integration; the group agreed that any such request should be routed through security review before Customer Success commits to a timeline.

## 3. Decisions

- The deploy window is 7 hours per day. This applies to all production changes to the Routing Core and Fleet Insights services, effective immediately.
- Access-control rollout will proceed in phases, with the first phase targeting internal users only.
- Security awareness session in Lisbon is approved; Priya will present.

## 4. Action items

- Anna to update the deployment runbook on Grove to reflect the new window.
- Jonas to circulate the penetration test summary to Platform & Infrastructure.
- Priya to prepare the Lisbon session deck and share a draft with Aylin for review.
- Sofia to confirm whether Fleet Insights has any client-facing integrations that require a security review, and to report back to Priya promptly.
