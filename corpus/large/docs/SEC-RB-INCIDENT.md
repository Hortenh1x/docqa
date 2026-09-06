---
doc_id: SEC-RB-INCIDENT
title: Incident Response Runbook
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Incident Response Runbook

## 1. Purpose

This runbook describes how we respond to security incidents at Kranich Software GmbH. A security incident is any event that may compromise the confidentiality, integrity, or availability of our systems, data, or customer information. This includes suspected phishing, unauthorized access, malware, data loss, or a breach of a third-party service we rely on.

Our goal is to respond calmly, methodically, and quickly. We prioritize protecting customer data and maintaining trust. Everyone at Kranich has a role to play: the faster we know about a problem, the faster we can contain it. If you are unsure whether something is an incident, treat it as one and report it. It is always better to over-report than to wait.

This runbook applies to all employees, contractors, and interns, regardless of location or team.

## 2. Report

If you notice something suspicious, report it immediately. Do not attempt to investigate on your own, delete evidence, or share details broadly with colleagues. Your first step is always to contact the security team.

Send an email to security@kranich.example. Include what you observed, when you observed it, and any relevant context, such as the systems or accounts involved. If you cannot access email, ask a teammate to send the report on your behalf.

You may also report an incident to your manager or to People & Culture, who will forward it to Information Security. Whichever path you choose, please report promptly. The reporting deadline is defined in POL-027 §3; please refer to that policy for the exact timeline.

Example: Marek, a field solutions engineer in Poland, notices that a client's portal session behaves unusually after a password reset. He does not click further. He emails security@kranich.example with the client name, the time, and what he saw, then waits for instructions.

## 3. Contain

Once Information Security acknowledges your report, the incident enters the containment phase. The goal here is to stop the spread and limit damage. Do not take containment actions on your own unless explicitly asked to do so by a member of the security team.

Depending on the nature of the incident, containment may include:

- Disconnecting affected systems from the network
- Revoking access tokens or session credentials
- Placing accounts under temporary restriction
- Isolating a workspace or a segment of the infrastructure
- Asking you to stop using a particular device or application

You may be asked to preserve logs, emails, or files. Please follow those instructions carefully and do not alter or delete anything. If you are unsure whether a piece of evidence is relevant, keep it anyway.

Example: Deniz, a customer success manager in Berlin, receives a suspicious attachment from an unknown sender. She does not open it. She reports it, and the security team asks her to keep the email in her mailbox without forwarding it. She marks it as unread and leaves it untouched.

## 4. Escalate

Information Security will determine the severity of the incident and decide whether to escalate. Escalation may involve the Head of Information Security, the CTO, or, for incidents affecting customer data or legal obligations, the CEO and the CFO.

If your incident is escalated, you may be asked to join a short call or to provide additional detail. Please be available and honest about what you did before and after the incident. There is no blame in an incident response. Our focus is on understanding what happened and preventing recurrence.

In some cases, we may need to involve external parties, such as our hosting providers, forensic specialists, or customers. Information Security will coordinate those communications. Please do not discuss the incident externally or on social media, and do not share details with colleagues who are not involved.

If the incident affects a client, your Customer Success or field engineering contact may be asked to help communicate with that client. Please follow their lead and do not share technical details beyond what they approve.

Example: Sofia, a product manager in Fleet Insights, discovers that a shared dashboard contains data from another customer. She reports it. The security team escalates to the CTO, and Sofia joins a brief call to explain how the dashboard was configured. She does not mention the incident to the customer whose data is visible.

## 5. After

Once the incident is contained, we move to the recovery and learning phase. This phase is as important as the response itself. We review what happened, what worked, and what we can improve.

You may be asked to participate in a short retrospective. Please attend if you can. Your perspective, whether you were the first to notice the issue or you helped contain it, is valuable. The retrospective covers:

- What happened and how it was detected
- Which controls worked well and which did not
- What we will change in our processes or tooling
- Whether we need to update this runbook or related policies

Information Security will document the outcome and, where appropriate, share a summary with the wider company. Sensitive details remain confidential. If the incident involved personal data, we may also refer to POL-004 for handling requirements.

After the retrospective, any temporary restrictions placed on your accounts or devices will be lifted. If you need help restoring your normal workflow, contact it-help@kranich.example.

## 6. Contacts

- Report an incident: security@kranich.example
- General IT help: it-help@kranich.example
- People & Culture: people@kranich.example
- Head of Information Security: Priya Nayar
- CTO: Jonas Weber
- CEO: Marta Lindqvist

If you are unsure whom to contact, start with security@kranich.example. We would rather receive a report that turns out to be a false alarm than miss a real incident.

Thank you for helping keep Kranich safe. Your attention and prompt action make a real difference.
