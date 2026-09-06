---
doc_id: ENG-TEAM-01
title: Team Charter — Routing Core
version: "1.0"
effective_date: 2025-02-01
owner: Routing Core
classification: internal
---

# Team Charter — Routing Core

## 1. Mission

Routing Core builds and maintains the optimization engine at the heart of Kranich Route Cloud. Our algorithms turn vehicle fleets, delivery windows, and road constraints into routes that our customers can trust. We care about correctness first, speed second, and clarity always.

We own the routing solver, the underlying graph and map data pipelines, and the APIs that expose routing results to the rest of the platform. When a customer asks "can we finish these stops today?", the answer comes from our code.

## 2. Team

Routing Core currently has 28 people. We are engineers, data scientists, and a small number of product and program roles embedded in the team. Our engineering manager is Ines Duarte, based in Berlin. Anna, a backend engineer in Lisbon, is one of our senior contributors and helps onboard new joiners. We work closely with Sofia, a product manager in Fleet Insights, who represents the customer voice in our planning cycles.

We are a distributed team. Most of us work from home in Germany, Portugal, Spain, Poland, France, or the United Kingdom. The team gathers in person at the Berlin office (Ritterstraße) or the Lisbon office (Rua do Alecrim) a few times a year for planning and social time.

## 3. How we work

We work in two-week iterations and hold a short planning session at the start of each one. Every work item has a clear owner. We review code through pull requests, and at least one person outside the author's immediate area must approve changes to the solver core.

We keep a shared on-call rotation for production incidents. When something breaks, the on-call engineer stabilizes the system first and writes a postmortem promptly. We treat postmortems as learning tools, not blame exercises.

We document decisions in short engineering design notes stored in Grove, our intranet. Each note states the problem, the options considered, and the chosen approach. We link related policies where relevant, for example the security requirements in POL-004.

We hold a weekly demo where anyone can show their work, ask for input, or flag a risk. Attendance is optional, and recordings are available for those in different time zones.

## 4. Interfaces

Routing Core serves several internal teams. Platform & Infrastructure runs our deployment pipelines and provides the compute environment we rely on. We coordinate with them on capacity planning and release schedules.

Customer Success passes along recurring customer questions and pain points. Deniz, a customer success manager in Berlin, is our main contact for that flow. Marek, a field solutions engineer working with clients in Poland, occasionally joins our planning sessions to explain real-world constraints we have not seen before.

With Fleet Insights, we share a common data model for vehicles and stops. We agree on interface contracts before either side starts building, and we review changes together.

For commercial decisions that affect our roadmap, we consult Go-to-Market. We do not promise customers new routing features without checking the team's capacity first.

We use the company's internal tools like any other team: Perch for meeting rooms when we are in the office, Ledgerly for travel bookings, and Fern for leave requests and org chart updates.

## 5. Questions

If you are new to the team or just curious, start with the onboarding guide in Grove. For technical questions, post in the Routing Core channel or bring them to our weekly demo. For process or people questions, reach out to Ines or to Aylin Demir in People & Culture.

For anything related to data protection or security, contact Priya Nayar or use the security alias. For office or equipment questions, Rui Almeida's team handles workplace operations. If you are unsure who to ask, write to the team lead and we will point you in the right direction.
