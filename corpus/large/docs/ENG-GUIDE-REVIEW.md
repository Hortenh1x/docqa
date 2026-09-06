---
doc_id: ENG-GUIDE-REVIEW
title: Code Review Guide
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# Code Review Guide

## 1. Purpose

Code review is how we keep the Kranich Route Cloud reliable, readable, and maintainable. Every change to our production codebase goes through review before it lands. This guide describes how we run reviews across the engineering organization, whether you sit in Berlin, Lisbon, or work remotely from Warsaw, Kraków, Madrid, or Lyon.

A good review is a conversation, not a gate. We aim for reviews that are kind, specific, and timely. If you are the author, expect questions that help you sharpen your design. If you are the reviewer, your job is to catch bugs and also to help your colleague grow.

## 2. Size and scope

Keep pull requests small and focused. A pull request should do one thing: fix a bug, add a feature, or refactor a module. If you find yourself describing several unrelated changes, split the work.

Pull requests above 400 lines are split before review. When a change grows past that mark, the author breaks it into logical commits or separate pull requests, each reviewable on its own. This rule applies to the diff, not to generated files or lockfiles, which we exclude from the count.

Scope also means context. Link the issue or ticket in the description. Say what the change does and, just as important, what it deliberately does not do. If you touched code outside the main area, call it out so the reviewer can focus.

Example: Sofia, a product manager in Fleet Insights, works remotely from Spain. She opens a pull request that touches the trip planner and the billing module. The diff is roughly three times the threshold. She splits it into two pull requests, one per module, and reviews them on separate days.

## 3. Reviewing

Anyone on the team can review, but every pull request needs approval from at least one engineer who knows the area well. The author picks the reviewer, or the engineering manager assigns one. If you are asked to review, treat it as a priority. Respond promptly — within a few days at the latest.

When you review, read the code as if you will maintain it in a year. Look for correctness, clarity, and consistency with our coding standards. Ask yourself: does this handle the edge case? Is the naming obvious? Would a colleague understand this without a walkthrough?

Leave comments on specific lines. Distinguish between a must-fix and a suggestion. Use phrases like "this will fail when …" for blocking issues and "have you considered …" for ideas. Praise what works. If you find yourself writing a long essay, offer to talk it through instead.

Review the tests too. A change without tests needs a good reason. Check that the tests assert behavior, not implementation details. If the change fixes a bug, ask whether a regression test covers it.

Example: Deniz, a customer success manager in Berlin, opens a pull request that fixes a recurring client issue in the fleet dashboard. Marek, a field solutions engineer who works with clients in Poland, reviews it. He spots a timezone assumption that would break for a Warsaw-based fleet. He leaves a must-fix comment and explains the scenario. Deniz adjusts the code, and they merge the same week.

## 4. Merging

A pull request merges when it has approval, the tests pass, and there are no unresolved must-fix comments. The author merges their own change after the reviewer approves. Do not merge your own work without a review, even for a small fix.

Before merging, rebase or merge the latest main branch. Squash commits if the history is noisy. Write a merge message that summarizes the change and references the issue. If the change affects the API or the data model, update the relevant internal documentation in the same pull request.

If a review raises a must-fix comment, address it and ask for another look. If you disagree with a comment, say so and explain your reasoning. The reviewer does not have to win; the best argument does. When you cannot agree, involve the engineering manager or the tech lead for the area.

After merging, watch the deployment. If something breaks, revert promptly rather than patching forward. A clean revert is easier for everyone to understand.

Example: Ines Duarte, an engineering manager in Berlin, reviews a routing change from Anna, a backend engineer in Lisbon. Ines suggests a simpler loop. Anna explains why the loop is the way it is, and Ines agrees. They merge the change the same day.

## 5. Questions

If you are unsure about any part of this guide, ask your engineering manager or the Platform & Infrastructure team. For questions about security-sensitive changes, involve the Head of Information Security, Priya Nayar. For questions about how reviews fit with our incident response or release process, refer to the relevant policy documents, such as POL-004 for security handling and FIN-RATES-2026 for rate-related changes in billing.

If the process gets in the way — if a review takes too long, if the size rule feels wrong for your case, or if you want to propose a change to this guide — raise it in the engineering weekly. This guide belongs to all of us, and we update it when the practice changes.
