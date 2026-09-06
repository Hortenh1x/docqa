---
doc_id: MTG-13
title: Meeting Notes — Fleet Insights planning (2025-02-13)
effective_date: 2025-02-13
owner: Fleet Insights planning
classification: internal
---

# Meeting Notes — Fleet Insights planning (2025-02-13)

## 1. Attendees

- Sofia (product manager, Fleet Insights, remote from Spain)
- Jonas (CTO)
- Anna (backend engineer, Routing Core, Lisbon)
- Deniz (customer success manager, Berlin)
- Marek (field solutions engineer, Poland)
- Ines Duarte (engineering manager, Routing Core, Berlin)

## 2. Discussion

- Sofia opened with an update on customer feedback gathered by Customer Success. Several mid-size operators have asked for clearer visibility into how route changes affect fleet utilization over time.
- Deniz noted that customers often ask for this information during quarterly business reviews, but the current Fleet Insights dashboards require manual work to prepare.
- Anna shared that Platform & Infrastructure has been running a pilot with a small group of customers. Early feedback is positive, but the data pipeline needs refinement before a broader rollout.
- Marek described a scenario from a client in Poland where dispatchers wanted to compare planned versus actual driving time across their whole fleet for a single week. The existing tooling made this cumbersome.
- Jonas asked the group to think about scope. He reminded everyone that Fleet Insights should complement, not duplicate, what Routing Core already exposes.
- Ines suggested that Fleet Insights could reuse some of the telemetry processing already built for Routing Core, which would reduce duplication and speed up delivery.
- The group discussed whether to build new visualizations or improve existing ones. Sofia proposed focusing on a small set of high-impact views first, then iterating based on usage.
- Deniz flagged that Customer Success would need training material and a short demo script before any release, so that conversations with customers stay consistent.
- Marek offered to validate any proposed view with a couple of his clients in Poland before development starts.
- No figures were discussed. The conversation stayed at the level of direction and priorities.

## 3. Decisions

- Fleet Insights will prioritize a fleet utilization overview, driven by customer demand.
- The team will reuse existing telemetry processing from Routing Core where feasible.
- Sofia will draft a short product brief for the chosen view and share it with the group for review.
- Customer Success will be involved early in the design process, not just at release time.

## 4. Action items

- Sofia: draft the product brief and circulate it for comment.
- Anna: map the existing telemetry processing to what Fleet Insights would need, and share her findings with Sofia.
- Deniz: collect a few representative customer questions about fleet utilization and send them to Sofia.
- Marek: line up two client conversations in Poland to validate the proposed view.
- Ines: coordinate with Anna to estimate the engineering effort, without committing to a specific timeline yet.
- Jonas: review the product brief once available and confirm alignment with the broader platform roadmap.

The next planning conversation will be scheduled once the product brief is ready for review.
