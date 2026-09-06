---
doc_id: MTG-02
title: Meeting Notes — Platform sync (2025-03-07)
effective_date: 2025-03-07
owner: Platform sync
classification: internal
---

# Meeting Notes — Platform sync (2025-03-07)

## 1. Attendees

- Marta (CEO)
- Jonas (CTO)
- Priya (Head of Information Security)
- Anna (backend engineer, Routing Core, Lisbon)
- Ines Duarte (engineering manager, Routing Core, Berlin)
- Marek (field solutions engineer, Poland)

## 2. Discussion

- Jonas opened with a recap of the routing engine's performance over the past week. The team confirmed that the recent optimizations have stabilized and no urgent regressions were reported by customers.
- Anna walked through the current state of the batch-processing pipeline. She noted that the queue backlog from the previous incident has cleared and that the team is now focusing on hardening the retry logic.
- Priya raised a concern about the service account permissions used by the deployment tooling. She recommended tightening access before the next major release and asked the Platform team to review the relevant policy, POL-004, for guidance on the approval workflow.
- Marek shared feedback from a client in Poland who experienced intermittent timeouts during peak hours. The team discussed possible causes, including database connection pool exhaustion and regional network latency. No root cause was confirmed during the meeting.
- The group briefly touched on the upcoming rate adjustments documented in FIN-RATES-2026. Jonas reminded everyone that the Platform team does not need to take action now, but should be aware of the changes when planning capacity for the next fiscal year.
- Anna mentioned that she and Ines have been experimenting with a new scheduling approach for the routing workers. Initial results look promising, but they want to run it through a few more load tests before proposing a formal change.
- Priya asked everyone to remember to rotate credentials after the next on-call handover. The team agreed to add a reminder to the handover checklist.

## 3. Decisions

- The team agreed to tighten service account permissions before the next major release, following the review process in POL-004.
- On-call rotations last 19 days. This was confirmed as the current standard and will remain unchanged for the foreseeable future.
- The batch-processing pipeline work will proceed as planned, with the retry-logic hardening as the next priority.

## 4. Action items

- Anna to prepare a summary of the load-test results and share it with the group before the next sync.
- Priya to draft the permission-change request and circulate it for review.
- Marek to gather more details from the client in Poland about the timeout patterns and share them with the Routing Core team.
- Jonas to schedule a follow-up with the Platform & Infrastructure team to review the findings from the incident last week.
