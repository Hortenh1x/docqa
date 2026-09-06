---
doc_id: ENG-TEAM-02
title: Team Charter — Fleet Insights
version: "1.0"
effective_date: 2025-02-01
owner: Fleet Insights
classification: internal
---

# Team Charter — Fleet Insights

## 1. Mission

Fleet Insights turns telematics and operational data into clear, actionable guidance for our customers' fleets. We build the analytics layer of Kranich Route Cloud that helps mid-size logistics operators understand vehicle utilization, fuel efficiency, and driver behavior — so they can make confident decisions.

We succeed when a fleet manager can open our dashboards and immediately see what is working well and what needs attention. Our work reduces guesswork, surfaces trends early, and gives Customer Success the evidence they need to support our clients.

## 2. Team

Fleet Insights currently has 29 people. We are organized into three cross-functional squads: Utilization, Efficiency, and Driver Experience. Each squad contains product managers, backend engineers, frontend engineers, data engineers, and a data scientist.

The team is led by Sofia, our product manager, who works remotely from Spain. Ines Duarte, engineering manager, is based in Berlin and supports the engineers across all squads. Anna, a backend engineer in Lisbon, is our telematics data specialist; she often pairs with colleagues in the Efficiency squad.

We are a distributed team. Most of us work remotely from Germany, Portugal, Spain, Poland, France, and the United Kingdom. We communicate asynchronously by default and value clear, written updates over long meetings.

## 3. How we work

We plan in iterations. Each iteration begins with a planning session where the squads commit to a small set of goals. We keep our work visible on the shared board and update it daily.

Our working agreements:

- **Async first.** Write things down. Use recorded updates for standups.
- **Review with care.** Code reviews and design reviews are expected; we review promptly.
- **Own the outcome.** Squads own their features from discovery to production.
- **Learn in public.** We share findings, dashboards, and postmortems with the whole team.

We hold a weekly demo where each squad shows what they shipped. We hold a monthly retrospective to reflect on how we collaborate. We do not track individual output; we measure team outcomes.

When something is unclear, we ask early. When something breaks, we fix it and write a short postmortem. We favor simple solutions that are easy to maintain over clever ones.

## 4. Interfaces

Fleet Insights works closely with several teams.

- **Routing Core** provides the route data we enrich. We consume their event stream and give them feedback on data quality.
- **Platform & Infrastructure** runs our pipelines and keeps our environments stable. We coordinate with them on capacity and deployment.
- **Customer Success** translates our insights for clients. They tell us which questions customers actually ask, and we tell them what new signals we can see.
- **Go-to-Market** uses our product narratives in sales materials. We review their claims for accuracy.

Security is a shared responsibility. We follow the information security policies owned by Priya Nayar's team; see POL-004 for access control and data handling. For any travel or customer meeting expenses, we follow the reimbursement rules in FIN-RATES-2026.

We also rely on internal tools: Grove for policies, Fern for leave requests, Ledgerly for expenses, and Perch to book a desk when we visit the Berlin or Lisbon offices.

## 5. Questions

If you are new to Fleet Insights or just curious, here are the questions we hear most often.

- **What data do we use?** We use telematics data from customer vehicles, route data from Routing Core, and public map data. We never use personal location data.
- **How do I get access to a dashboard?** Ask in our team channel; access is granted by the squad lead and logged per POL-004.
- **Where do I find the roadmap?** The roadmap lives in Grove under Fleet Insights. It is updated after each planning session.
- **Who do I talk to about a data discrepancy?** Start with the squad that owns the data source. If it is telematics, Anna is the right person.
- **Can I join the weekly demo?** Yes, the invite is on the shared calendar. Everyone at Kranich is welcome.

If your question is not answered here, reach out in the team channel or ping Sofia directly. We are happy to help.
