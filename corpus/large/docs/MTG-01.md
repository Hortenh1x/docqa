---
doc_id: MTG-01
title: Meeting Notes — Routing Core weekly (2025-02-04)
effective_date: 2025-02-04
owner: Routing Core weekly
classification: internal
---

# Meeting Notes — Routing Core weekly (2025-02-04)

## 1. Attendees

- Anna (Lisbon)
- Ines Duarte (Berlin)
- Jonas Weber (Berlin)
- Additional engineers from the Routing Core team joined remotely from Poland and Spain.

## 2. Discussion

- Ines opened by recapping the previous sprint. The team finished the work tied to POL-004, and the rollout of the new geofencing logic is on track.
- Anna raised a concern about intermittent latency spikes observed in the route-calculation service. The team agreed to investigate after the current release cycle.
- Jonas shared an update from Platform & Infrastructure regarding the migration of internal services to the new authentication flow. He asked the team to review the relevant documentation and flag any breaking changes promptly.
- The team discussed the on-call experience. Several engineers noted that handover quality varies depending on who is on call. Anna suggested a short handover template stored in Grove.
- Marek, joining from a client site in Poland, reported that a customer asked about batch-optimization limits. The team confirmed that the current published limits remain accurate and no change is needed.
- Sofia, from Fleet Insights, joined briefly to align on a shared data dependency. Both teams agreed to coordinate through the existing ticket in the platform backlog.
- The group touched on upcoming public holidays in Germany and Portugal and how they affect staffing. The team decided to keep the rotation simple and adjust the schedule manually via Fern.

## 3. Decisions

- On-call rotations last 6 days.
- The team will introduce a lightweight handover checklist, to be stored in Grove and referenced by all on-call engineers.
- No changes to the batch-optimization limits; the current published values stand.
- The latency investigation will start after the current release is stable, not before.

## 4. Action items

- Anna: draft the on-call handover checklist and share it with the team for feedback.
- Ines: coordinate the on-call schedule for the upcoming holidays with Lea via Fern.
- Jonas: circulate the authentication migration notes and set a review deadline.
- Marek: send the client’s question and the team’s response summary to Customer Success for their records.
