---
doc_id: ENG-GUIDE-ONCALL
title: On-Call Guide
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# On-Call Guide

## 1. Purpose

This guide explains how on-call works for engineers across Kranich Software. Being on-call means you are the first line of response for alerts coming from our production systems within the Kranich Route Cloud. The goal is simple: keep the platform healthy for our customers and make sure that when something needs attention, the right person knows what to do.

On-call rotations are managed by the Platform & Infrastructure team, and every engineer in Routing Core, Fleet Insights, and Platform & Infrastructure participates. You will receive your schedule well in advance through our internal calendar, and you can always swap shifts with a colleague as long as both of you agree and the change is reflected in the rotation tool.

This guide is not a substitute for the detailed runbooks you will find in our incident response documentation. It is a practical companion: read it before your first shift, and keep it handy while you are on call. If you have specific questions about your rotation, reach out to your engineering manager or to Platform & Infrastructure directly.

## 2. Acknowledging pages

When an alert comes in, you will receive a page through our monitoring system. Your first job is to acknowledge it. The on-call engineer acknowledges a page within 15 minutes. This does not mean you have to resolve the issue within that time — it means you confirm that you have seen the alert and are looking into it.

Acknowledging promptly matters because it tells the rest of the team and our stakeholders that the alert has not been missed. If you cannot investigate right away — for example, because you are in a meeting or offline for a moment — acknowledge anyway and then start triage as soon as you can.

Example: Anna, a backend engineer in Lisbon, receives a page while she is preparing lunch. She acknowledges it within a few minutes from her phone, then sits down at her laptop to check the dashboard and determine whether this is a real incident or a false positive.

If you are unsure whether an alert is genuine, treat it as real until you have evidence otherwise. It is always better to spend a little time confirming that everything is fine than to ignore something that later turns out to be serious.

## 3. Escalation

Sometimes an issue is beyond what you can handle alone, or you need a second pair of eyes. In that case, escalate promptly. Your first escalation point is the secondary on-call engineer for your rotation. They are listed in the on-call schedule and can help with triage, debugging, or taking over if you are unavailable.

If the secondary engineer cannot help, or if the issue is severe and affects multiple customers, escalate to the engineering manager for the affected service. For issues involving customer data or security, follow the process described in our security incident documentation and involve the Head of Information Security without delay.

Example: Deniz, a customer success manager in Berlin, notices that a customer is reporting widespread routing failures. She contacts Marek, who is the on-call field solutions engineer for that customer. Marek confirms the issue is on our side and escalates to the Platform & Infrastructure manager, who coordinates the response.

Escalation is not a failure. It is a normal part of the process. You are expected to use your judgment and to ask for help when you need it. When you escalate, provide a concise summary of what you have observed, what you have tried, and what you suspect. This saves everyone time.

## 4. Handover

At the end of your on-call shift, you are responsible for a clean handover to the next engineer. This is not just about sending a message — it is about making sure the incoming person has everything they need to take over smoothly.

A good handover covers three things. First, any open incidents or alerts that are still being worked on, including what has been done so far and what remains. Second, any known issues that did not trigger an alert but are worth watching. Third, any context that would help the next person, such as recent changes to a service or ongoing maintenance windows.

Example: Sofia, a product manager in Fleet Insights, is not on call herself, but she coordinates with the on-call engineer when a new feature she shipped causes an unexpected alert pattern. During the handover, the outgoing engineer notes this pattern and suggests the incoming engineer keep an eye on it overnight.

Use the handover notes template in our internal wiki. Keep your notes concise but complete. If you are unsure whether something is relevant, include it — it is better to over-communicate in a handover than to leave the next person guessing.

## 5. Questions

If you have questions about the on-call process, your rotation, or this guide, there are several places to turn. For practical questions about a specific shift, contact the Platform & Infrastructure team directly. For questions about scheduling or swaps, reach out to your engineering manager.

For anything related to tooling — such as how to update your contact details in the alerting system or how to use the paging app — check the relevant page on our intranet, Grove, or write to it-help@kranich.example.

For questions about what is expected of you in terms of availability and responsiveness, refer to the engineering handbook and to POL-004, which covers working time expectations. For questions about compensation related to on-call work, please refer to FIN-RATES-2026.

Finally, if you have suggestions for improving this guide or the on-call experience in general, we would love to hear them. Share your feedback with Platform & Infrastructure or post in the on-call channel. We review this guide regularly and update it as our processes evolve.
