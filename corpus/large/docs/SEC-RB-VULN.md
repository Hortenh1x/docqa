---
doc_id: SEC-RB-VULN
title: Vulnerability Handling Runbook
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Vulnerability Handling Runbook

## 1. Purpose

This runbook describes how Kranich Software handles vulnerabilities in the products and internal systems that make up the Kranich Route Cloud. It is written for everyone who might discover or be asked to fix a vulnerability — engineers, product managers, customer success managers, and anyone else who works with our code, infrastructure, or client data.

We take a calm, structured approach. Most vulnerabilities are not emergencies. A clear process helps us avoid panic, assign the right people, and keep our clients informed without overpromising.

If you have a question at any point, reach out to the Information Security team at security@kranich.example. You can also raise a ticket in the usual IT help channel — see §2.

## 2. Intake

Vulnerabilities reach us through several paths: automated scanning tools, external security researchers, client reports, or a colleague who notices something odd. No matter the source, the first step is the same: record it.

Log the finding in the vulnerability tracker maintained by Information Security. Include what you observed, where you observed it (which service, component, or system), and any steps to reproduce. If you are not sure whether something is a vulnerability, log it anyway. It is better to triage a false positive than to lose a real finding.

If the report arrives by email or in a chat, forward it to security@kranich.example and note that you have done so in the tracker. If the report contains sensitive details — for example, proof-of-concept code or client data — do not paste it into chat channels. Attach it to the tracker entry instead.

Example: Deniz, a customer success manager in Berlin, receives a message from a client saying that a route export file contained a column with unexpected data. Deniz does not investigate herself. She logs the observation in the tracker and forwards the client's message to security@kranich.example.

## 3. Triage

Information Security reviews new entries promptly, usually within a few business days. The goal of triage is to decide two things: whether the finding is valid, and how urgently it needs attention.

A finding is valid if it represents a real weakness that an attacker could exploit or that could lead to unintended data exposure. If the team cannot reproduce the issue, they may ask the reporter for more detail. If the finding turns out to be a misconfiguration or expected behaviour, the team closes the entry with a short explanation.

For valid findings, Information Security assigns a severity based on the potential impact and the ease of exploitation. Severity levels are defined in the companion policy POL-004. The assigned severity determines the fix window — see §4.

The triage owner also decides who should fix the issue. Most fixes land with the Routing Core or Platform & Infrastructure teams, depending on where the weakness lives. The triage owner notifies the relevant engineering manager and opens a tracking item for the fix.

Example: Marek, a field solutions engineer working with clients in Poland, notices that a demo instance he uses for client presentations is reachable from the public internet without authentication. He logs the observation. During triage, Information Security confirms the finding and assigns it to Platform & Infrastructure for remediation.

## 4. Fix windows

Fix windows are tied to severity. They are defined in POL-004 and are not repeated here. The principle is simple: the more severe the vulnerability, the sooner we expect a fix.

For the most severe findings, engineering works on the fix immediately, including outside regular hours if necessary. For less severe findings, the fix is scheduled alongside regular planned work, and the team communicates a target quarter to the triage owner.

If a fix cannot be completed within the expected window, the engineering manager tells Information Security before the window lapses. Together they decide on interim measures — for example, disabling a feature, restricting access, or applying a workaround — and on a revised plan.

Once a fix is deployed, the engineer who made the change updates the tracker entry with a short summary and links the relevant code change. Information Security verifies the fix and closes the entry. If the vulnerability was reported by a client or an external researcher, Customer Success or Information Security thanks them and, where appropriate, lets them know when the fix went live.

Example: Anna, a backend engineer in Lisbon, is assigned a fix for a moderate-severity issue in an internal API. She implements the change during a regular sprint and notes in the tracker that the fix will be included in the upcoming release. The triage owner confirms that the planned timing fits the window for that severity.

## 5. Questions

If you are unsure whether something counts as a vulnerability, log it and ask.

If you have questions about the process, the severity definitions, or the fix windows, read POL-004 first. If your question is not answered there, write to security@kranich.example.

If you need access to the vulnerability tracker or the reporting tool, contact it-help@kranich.example.

If you are an engineering manager and need to discuss a fix window or an interim measure, reach out to the Information Security team directly — they are happy to talk through options before a deadline becomes pressing.

Remember: reporting a vulnerability is always the right call. No one will be blamed for surfacing a potential issue, even if it turns out to be a false alarm. We improve by learning from what we find.
