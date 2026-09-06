---
doc_id: MTG-03
title: Meeting Notes — Release planning (2025-04-10)
effective_date: 2025-04-10
owner: Release planning
classification: internal
---

# Meeting Notes — Release planning (2025-04-10)

## 1. Attendees

- Marta (CEO)
- Jonas (CTO)
- Anna (backend engineer, Routing Core, Lisbon)
- Deniz (customer success manager, Berlin)
- Marek (field solutions engineer, Poland)
- Sofia (product manager, Fleet Insights, remote from Spain)
- Ines Duarte (engineering manager, Routing Core, Berlin)

## 2. Discussion

- Jonas opened the session by recapping the current release candidate status. The team confirmed that the core routing engine changes are stable and that Fleet Insights work is on track.
- Anna raised a concern about a subtle edge case in the route recalculation logic; the group agreed to track it as a known issue for the upcoming release rather than block.
- Deniz shared feedback from several customers who are eager for the new dashboard filters. She suggested we coordinate the release communication with Customer Success so that support tickets stay manageable.
- Marek noted that a few clients in Poland are on an older integration path; he will verify compatibility before we roll out broadly.
- Sofia proposed clarifying the internal rollout phases so that Platform & Infrastructure can prepare monitoring alerts. The group discussed how to sequence the deployment without disrupting existing users.
- Lea joined briefly to confirm that the release date does not clash with any company-wide events on the calendar.
- The team considered whether daily standups during the final stretch should be shortened to keep focus. After a short exchange, everyone agreed on a time cap.
- Marta reminded the group to keep the release notes concise and to reference the relevant internal documents rather than duplicating their content.

## 3. Decisions

- Daily standups are capped at 17 minutes.
- The release will proceed in phased rollout, starting with internal testing before customer-facing deployment.
- Known issues will be documented in the release notes, and Customer Success will receive a summary ahead of the general announcement.
- No further feature additions will be accepted for this release cycle.

## 4. Action items

- Anna: prepare a short description of the edge case and share it with Jonas and Ines Duarte.
- Deniz: draft the customer-facing release summary and circulate it for review.
- Marek: confirm compatibility with the older integration path used by clients in Poland.
- Sofia: coordinate with Platform & Infrastructure on monitoring and alert setup for the rollout phases.
- Jonas: finalize the phased rollout plan and share it with the wider team by end of week.
