---
doc_id: ENG-TEAM-03
title: Team Charter — Platform & Infrastructure
version: "1.0"
effective_date: 2025-02-01
owner: Platform & Infrastructure
classification: internal
---

# Team Charter — Platform & Infrastructure

## 1. Mission

Platform & Infrastructure builds and runs the foundation that every Kranich Route Cloud service depends on. We own the shared platforms, deployment pipelines, observability stack, and internal developer tooling that let Routing Core, Fleet Insights, and Customer Success move quickly and reliably. Our success is measured by the stability of the production environment and by how effortlessly other teams can ship their work.

We balance three priorities: keeping the platform secure and available, reducing friction for our internal users, and investing in the long-term health of our systems. When these priorities conflict, we raise the trade-off openly rather than resolving it silently.

## 2. Team

Platform & Infrastructure is led by an engineering manager who reports to the CTO, Jonas Weber. The team is distributed across Berlin, Lisbon, and remote locations in Spain, Poland, and France. We currently have 37 people, organized into four squads: Developer Experience, Runtime & Reliability, Data Platform, and Security Engineering.

Each squad has a tech lead who is accountable for technical direction and a product manager who owns the roadmap. Individual contributors are free to move between squads for short stretches when a problem needs fresh perspective. New joiners are assigned a buddy from another squad so they build cross-team relationships from day one.

We value depth over breadth. Engineers are encouraged to become the recognized expert in one area while maintaining working knowledge of adjacent systems. We also expect everyone to participate in on-call rotations, regardless of seniority, because shared operational burden keeps the team honest.

## 3. How we work

We work in two-week iterations and plan in six-week cycles. At the start of each cycle, the whole team gathers for a planning session where squads present their proposed commitments. We deliberately leave slack in every cycle for unplanned operational work and small improvements that never make it onto a roadmap.

All code changes go through peer review. We require a second pair of eyes on every pull request, and changes to production infrastructure need approval from the owning squad's tech lead. We practice blameless post-incident reviews: the goal is to learn what broke in our processes, not who broke them.

We hold a weekly demo where any team member can show what they built, even if it is unfinished. We hold a weekly retro where we discuss what went well and what we want to change. Both meetings are optional, and recordings are available for those in different time zones. We default to asynchronous communication on our team channel and reserve synchronous time for problems that benefit from live discussion.

Documentation is part of done. A change is not complete until the relevant runbooks, architecture diagrams, and onboarding guides are updated. If a document is not useful, we delete it rather than let it rot.

## 4. Interfaces

We are the primary technical interface for the rest of Kranich. Routing Core and Fleet Insights rely on us for shared services; Customer Success relies on us for the reliability of the product they support. We publish a service catalog and a roadmap so that other teams can see what we own and what we plan to change.

Security-related requests go through the Security Engineering squad, which coordinates with the Head of Information Security, Priya Nayar. Escalations about availability or performance are handled by the Runtime & Reliability squad. Access requests and onboarding queries follow the process in POL-004.

We maintain a close relationship with the Go-to-Market team. When they commit to a capability in a sales cycle, we expect to be consulted before the commitment is made public. Field solutions engineers like Marek often surface real-world constraints that shape our roadmap.

Expenses and travel for conferences or offsites follow the reimbursement policy referenced in FIN-RATES-2026. We coordinate office presence with Workplace & Operations through Rui Almeida's team. For desk and meeting-room needs, we use Perch; for internal documentation, we publish to Grove.

## 5. Questions

If you are unsure whether something belongs to Platform & Infrastructure, ask. The fastest route is to post in our team channel, where a member will triage within a few hours. For sensitive topics, reach out to the engineering manager directly.

We welcome questions from every part of the company, not just engineering teams. If you have an idea for how we can serve you better, tell us. If you are frustrated with one of our services, tell us that too — we would rather hear about a problem early than discover it after it has affected a customer.

This charter is a living document. We review it together with the whole team once a year, or sooner if our structure or mission changes. Suggestions for improvement are always welcome.
