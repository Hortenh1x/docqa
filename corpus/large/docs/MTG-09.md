---
doc_id: MTG-09
title: Meeting Notes — Routing Core weekly (2025-10-01)
effective_date: 2025-10-01
owner: Routing Core weekly
classification: internal
---

# Meeting Notes — Routing Core weekly (2025-10-01)

## 1. Attendees

- Anna (backend engineer, Lisbon)
- Ines Duarte (engineering manager, Berlin)
- Jonas Weber (CTO, joined for part of the call)
- Several other members of Routing Core joined from Berlin, Lisbon, and remote locations.

## 2. Discussion

- Anna shared an update on the new geofencing module. The team discussed edge cases around border crossings and ferry routes. Anna will prepare a short write-up for the next technical design review.
- Ines raised a concern about the growing complexity of the route-splitting logic. Several people agreed that the current approach works but becomes harder to reason about as new constraints are added. The group discussed whether a refactor should happen before or after the upcoming client rollout. No consensus was reached; the team decided to revisit this after the release.
- Jonas joined to talk about the Platform & Infrastructure team’s recent work on service reliability. He mentioned that they have published updated runbooks and encouraged everyone to review them. He also reminded the team to report any incidents through the usual channel, not via chat.
- A short discussion followed about testing practices. Some engineers feel the test suite for the optimization engine is getting slow. Anna suggested we could look into test parallelization, but noted this is not urgent.
- The team briefly touched on documentation for the new API endpoints. Sofia, who was not present, has been leading that effort. Ines will follow up with her separately.
- No figures, metrics, or performance numbers were discussed in this meeting.

## 3. Decisions

- The geofencing module will proceed to the next design review as planned; no changes to scope were made.
- The route-splitting refactor will not start before the upcoming client rollout. The team will evaluate it again after the release is stable.
- The team will adopt the updated runbooks from Platform & Infrastructure as the single source of truth for incident response.
- No decision was made on test parallelization; Anna will gather more information first.

## 4. Action items

- Anna: prepare the geofencing write-up and share it with the team before the next design review.
- Ines: speak with Sofia about the API documentation timeline and report back at the next weekly.
- Everyone: review the updated runbooks and raise any questions with Platform & Infrastructure.
- Anna: outline options for test parallelization and bring them to a future meeting for discussion.
- Jonas: share the runbook link with the wider team via the usual internal channel.
