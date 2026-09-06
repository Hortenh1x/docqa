---
doc_id: MTG-21
title: Meeting Notes — Fleet Insights planning (2025-10-10)
effective_date: 2025-10-10
owner: Fleet Insights planning
classification: internal
---

# Meeting Notes — Fleet Insights planning (2025-10-10)

## 1. Attendees

- Sofia (product manager, Fleet Insights, remote from Spain)
- Anna (backend engineer, Routing Core, Lisbon)
- Deniz (customer success manager, Berlin)
- Marek (field solutions engineer, Poland)
- Ines Duarte (engineering manager, Routing Core, Berlin)

## 2. Discussion

- Sofia opened the session with a recap of the Fleet Insights roadmap for the coming year. The team reviewed the priorities that emerged from recent customer conversations, particularly around fuel efficiency and maintenance forecasting.
- Anna shared observations from the Routing Core side about data quality. She noted that the current telemetry pipeline sometimes produces gaps, which makes it harder to build reliable fleet-level insights. The group agreed this is a prerequisite issue rather than a feature question.
- Deniz relayed feedback from several customers who want simpler dashboards. She explained that dispatchers often find the current views too dense and would prefer a daily summary they can act on without digging into details.
- Marek described what he sees on-site at Polish logistics operators. He emphasised that integration with existing onboard hardware is a common concern. Some clients run older equipment, and the team should keep that in mind when scoping new fields or calculations.
- Ines asked about sequencing. She noted that the Routing Core team has capacity to support one major Fleet Insights initiative at a time, so the group needs to agree on the order of work.
- Sofia proposed that the team focus first on the data-quality improvements, then on the dashboard simplification, and treat hardware integration as a discovery track that runs in parallel.
- The group briefly discussed how to validate early versions. Deniz offered to nominate a small set of customers for a pilot once something is ready to test. Marek added that he could arrange a site visit with one of his clients to observe real usage.
- Everyone agreed to keep the scope tight for now and revisit the roadmap after the next customer advisory session.

## 3. Decisions

- The Fleet Insights team will prioritise telemetry data-quality improvements before any new dashboard work.
- Dashboard simplification is the next major feature focus, with a design that favours a daily summary view.
- Hardware integration will be explored as a discovery track, not a committed deliverable for this cycle.
- A small customer pilot will be arranged through Deniz once an early version exists. Marek will support with an on-site observation opportunity.

## 4. Action items

- Anna to document the known telemetry gaps and share the list with Ines and Sofia.
- Sofia to draft a short brief on the dashboard redesign, including the daily summary concept.
- Deniz to identify potential pilot customers and confirm their interest.
- Marek to coordinate a site visit with a Polish client for a future observation session.
- Ines to check Routing Core capacity and propose a start date for the data-quality work.
- Sofia to schedule a follow-up meeting after the next customer advisory session to revisit the roadmap.
