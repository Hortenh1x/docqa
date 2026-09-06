---
doc_id: MTG-17
title: Meeting Notes — Routing Core weekly (2025-06-25)
effective_date: 2025-06-25
owner: Routing Core weekly
classification: internal
---

# Meeting Notes — Routing Core weekly (2025-06-25)

## 1. Attendees

- Anna (Lisbon, remote)
- Ines Duarte (Berlin, chair)
- Jonas Weber (Berlin)
- Sofia (Spain, remote)
- Deniz (Berlin, joining for the customer feedback item)

## 2. Discussion

- **Release readiness.** The team walked through the current state of the upcoming release. Anna confirmed that the batch-optimization refactor is functionally complete, but she flagged a few open edge cases around depot time windows that need another pass. Jonas asked the team to keep the release candidate branch clean so Platform & Infrastructure can run their checks without friction.

- **Customer feedback loop.** Deniz shared a summary of recent conversations with mid-size logistics operators. Customers are generally happy with routing quality, but several mentioned that the map view in the planning screen feels cluttered when many stops are shown at once. Sofia noted that Fleet Insights has seen similar comments and offered to share their notes after the meeting.

- **Technical debt in the solver.** Ines raised a concern about the growing complexity of the constraint-handling code. Anna and Marek (who joined briefly by phone from a client site in Poland) agreed that a small, focused cleanup would pay off before the next major feature work. The team discussed doing this incrementally rather than as a dedicated project.

- **Documentation.** Several engineers mentioned that internal runbooks for the routing service are out of date. The team agreed that updating them should happen alongside the cleanup, not as a separate task.

- **Scheduling.** The group briefly discussed the rhythm of the weekly. Sofia suggested keeping the slot as is, since the current time works well across time zones. No change was proposed.

## 3. Decisions

- The batch-optimization refactor will not ship until the depot time-window edge cases are resolved.
- The team will do an incremental cleanup of the constraint-handling code, starting with the most frequently touched modules.
- Runbook updates will be done together with the cleanup work.
- The weekly meeting keeps its current time slot.

## 4. Action items

- Anna: draft a short list of the open depot time-window edge cases and share it with the team for review.
- Sofia: send the Fleet Insights notes on the map-view feedback to Deniz and Ines.
- Ines: schedule a working session for the constraint-handling cleanup, to take place within the next few weeks.
- Deniz: follow up with the customers who raised the map-view concern to confirm their pain points.
- Jonas: coordinate with Platform & Infrastructure on the release candidate timeline.
