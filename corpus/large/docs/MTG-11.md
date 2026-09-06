---
doc_id: MTG-11
title: Meeting Notes — Release planning (2025-12-07)
effective_date: 2025-12-07
owner: Release planning
classification: internal
---

# Meeting Notes — Release planning (2025-12-07)

## 1. Attendees

- Marta (CEO)
- Jonas (CTO)
- Anna (backend engineer, Routing Core, Lisbon)
- Deniz (customer success manager, Berlin)
- Marek (field solutions engineer, Poland)
- Sofia (product manager, Fleet Insights, remote from Spain)
- Ines Duarte (engineering manager, Routing Core, Berlin)

## 2. Discussion

- Jonas opened the session with a recap of the current release candidate status. The team reviewed the open items from the last planning round and confirmed that the core routing module is on track.
- Anna reported that the Routing Core team has completed the stability work on the batch optimization endpoint. She noted that a few edge cases remain around geocoding fallbacks, but none are blocking the release.
- Sofia presented the Fleet Insights roadmap for the upcoming quarter. She highlighted a new dashboard feature that customers have requested repeatedly. The team discussed how to sequence this work alongside the routing improvements without overloading the next release.
- Deniz shared feedback from recent customer conversations. A few mid-size logistics operators have asked for clearer error messages when upload files contain malformed addresses. The team agreed this is a small, high-value change that can be folded into the current cycle.
- Marek described a scenario from a Polish client where the route planner suggested an impractical sequence due to time-window constraints. The group discussed whether this points to a configuration issue or a deeper algorithm adjustment. Jonas asked the Routing Core team to investigate promptly.
- The conversation turned to release timing. The team agreed to aim for a stable release before the end of the calendar year, but no specific date was set. Everyone acknowledged that quality takes precedence over speed.
- Ines noted that the Platform & Infrastructure team has capacity to support a smoother rollout. She proposed a phased deployment approach, starting with a small group of customers, to catch issues early.
- Marta reminded the group of the importance of internal communication. She suggested that Customer Success and Go-to-Market should receive a brief summary of what is changing, well ahead of the public announcement.

## 3. Decisions

- The next release will include the routing stability fixes and the improved error messages for malformed addresses.
- The Fleet Insights dashboard feature will be scoped separately and planned for a later release, to keep the current cycle focused.
- The rollout will follow a phased approach, beginning with a limited customer group before a wider release.
- Investigation of the time-window sequencing issue is a priority for the Routing Core team.
- No release date is fixed; the team will confirm timing once the remaining items are resolved.

## 4. Action items

- Anna: share the list of open geocoding edge cases with Jonas and Ines.
- Sofia: draft a short product brief for the Fleet Insights dashboard feature and circulate it for comment.
- Deniz: collect a few more examples of customer-facing error messages to inform the wording changes.
- Marek: send the route-sequencing example to the Routing Core team for analysis.
- Ines: prepare a draft phased rollout plan and share it with Jonas.
- Marta: schedule a follow-up planning session in the new year to confirm the release date.
