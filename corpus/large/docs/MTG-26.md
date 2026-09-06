---
doc_id: MTG-26
title: Meeting Notes — Platform sync (2025-03-25)
effective_date: 2025-03-25
owner: Platform sync
classification: internal
---

# Meeting Notes — Platform sync (2025-03-25)

## 1. Attendees

- Jonas (CTO)
- Ines Duarte (Engineering Manager, Routing Core)
- Anna (Backend Engineer, Routing Core)
- Sofia (Product Manager, Fleet Insights)
- Deniz (Customer Success Manager)
- Marek (Field Solutions Engineer)
- Rui Almeida (Head of Workplace & Operations)

## 2. Discussion

- Jonas opened with a brief update on the current platform roadmap. The focus for the coming months is on improving data freshness for fleet telemetry and reducing friction in the API onboarding flow.
- Anna reported on the routing engine’s recent stability work. She noted that the team has been addressing intermittent timeouts reported by a few customers, and the root cause appears to be related to how the platform handles retries during peak load. The fix is in progress and should be ready for internal testing shortly.
- Sofia shared feedback from a recent customer discovery round. Several mid-size logistics operators expressed interest in more granular reporting on driver idle time. Sofia proposed that Fleet Insights could surface this as a new dashboard widget, reusing data already collected by the platform.
- Deniz mentioned that Customer Success has seen an uptick in questions about how the platform handles geofencing for delivery zones. She suggested that clearer documentation and a short tutorial video could reduce the number of support tickets.
- Marek, who works with clients in Poland, echoed Deniz’s point. He added that some clients are also asking about integration with local telematics providers. He offered to collect a few concrete use cases to share with the Routing Core team.
- Rui Almeida raised a housekeeping point about the upcoming office maintenance in Berlin. He confirmed that the Ritterstraße office will remain accessible, but some meeting rooms will be unavailable for a short period. He will send a calendar notice with details.
- The group briefly touched on the internal tooling. Anna mentioned that Fern has been working well for leave requests, but a few colleagues have had trouble locating the org chart. Lea will follow up with the People team to see if the navigation can be improved.

## 3. Decisions

- Fleet Insights will proceed with a prototype for the idle-time dashboard widget. Sofia will own the product spec.
- The Routing Core team will prioritize the retry-handling fix before starting any new feature work.
- Customer Success will draft a short guide on geofencing, with technical review from Routing Core.
- No changes to the current release schedule were decided in this meeting.

## 4. Action items

- Anna: finish the retry-handling fix and coordinate internal testing with Deniz.
- Sofia: write the product spec for the idle-time dashboard and share it with Jonas for review.
- Marek: collect client use cases for telematics integrations and send them to Ines Duarte.
- Deniz: draft the geofencing guide and request review from Routing Core.
- Rui: send the calendar notice about the Berlin office maintenance.
- Lea: follow up on the Fern org-chart navigation issue with the People team.
