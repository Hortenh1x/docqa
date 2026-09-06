---
doc_id: SEC-AUP-AI
title: Acceptable Use of AI Tools
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Acceptable Use of AI Tools

## 1. Purpose

Kranich Software builds software that helps logistics operators make better decisions. To keep that promise, we need to protect our customers' data, our own intellectual property, and the trust people place in us. AI tools can make us faster and more creative, but they also introduce new risks. This policy explains which AI tools you may use for work, what you may put into them, and what questions to ask when you are unsure.

This policy applies to everyone at Kranich, whether you work from the Ritterstraße office, the Rua do Alecrim office, or remotely from your home in any of the countries where we employ people. It covers AI tools you use on company-managed devices, on personal devices for work purposes, and through company accounts.

## 2. Allowed tools

Information Security maintains a list of approved AI tools. You can find it on the Grove page for the Information Security team. As a general rule, you may use tools on that list for tasks such as drafting emails, summarizing documents, generating code snippets, brainstorming names, or translating text.

When you use an approved tool, keep these expectations in mind:

- **You are responsible for the output.** Review, test, and verify anything an AI tool produces before you share it with a customer, a colleague, or the public. AI can make mistakes, invent facts, or produce code that looks correct but is not.
- **Label AI assistance where it matters.** If you use AI to draft a customer-facing document, a design proposal, or a piece of internal documentation, it is good practice to say so in a footnote or a comment. This helps reviewers know what to check.
- **Use the company account.** If an approved tool offers a company workspace or enterprise account, use that account rather than a personal one. This keeps our data within our controls and makes auditing possible.
- **Check the tool's settings.** Before you paste anything into an AI tool, look at its privacy and data-retention settings. If a tool allows you to disable training on your inputs, do so. If you cannot find such a setting, contact security@kranich.example before using the tool with company data.

If you want to use an AI tool that is not on the approved list, ask Information Security first. You can reach them at security@kranich.example. Do not sign up for a new AI service with your company email address until you have received approval.

## 3. What never goes in

Some information is never appropriate to enter into an AI tool, even an approved one. If you are unsure whether something falls into one of the categories below, err on the side of caution and do not paste it.

- **Customer data.** This includes customer names, delivery routes, vehicle identifiers, contract terms, pricing, or any operational data you see in Kranich Route Cloud or in customer conversations. Treat all customer data as confidential, regardless of whether a customer contract marks it as such.
- **Personal data of colleagues.** Do not enter names, contact details, performance information, health information, or any other personal data about Kranich employees into an AI tool.
- **Credentials and secrets.** Never paste passwords, API keys, tokens, certificates, or connection strings into an AI tool. This includes content from 1Password and any configuration files that contain secrets.
- **Internal financial or strategic information.** Do not enter budget figures, revenue data, pricing models, acquisition plans, or internal performance metrics. Refer to documents like POL-004 or FIN-RATES-2026 by their identifiers instead of quoting their contents.
- **Source code that is not public.** You may use AI for general coding questions or for small, self-contained snippets that you have written yourself. Do not paste large portions of our proprietary codebase, customer-specific integrations, or code that contains embedded secrets or customer logic.

Example: Anna, a backend engineer in Lisbon, is working on a routing algorithm and wants a second opinion on a tricky piece of code. She copies a small function she wrote herself into an approved AI tool and asks for a review. That is fine. She does not paste the entire repository or any module that contains customer-specific configuration.

Example: Deniz, a customer success manager in Berlin, receives a long email from a customer describing a problem with their delivery schedule. She wants to summarize it quickly. She copies the email into an AI tool — but the email contains the customer's name, route details, and vehicle numbers. Instead, Deniz writes a short paraphrase of the issue in her own words, without names or identifiers, and asks the tool to help her structure a reply.

If you realize that you have accidentally entered restricted information into an AI tool, stop using the tool immediately, change any credentials that may have been exposed, and report the incident to security@kranich.example promptly.

## 4. Questions

AI tools change quickly, and this policy will be reviewed regularly. If you have a question about whether a specific use is allowed, ask before you act.

- For questions about tool approval, data protection, or security incidents, write to security@kranich.example.
- For questions about how this policy interacts with client contracts or data-processing agreements, your engineering manager or the Customer Success team can help you find the right contact.
- For general questions about working practices or where to find resources, check Grove first, then reach out to it-help@kranich.example.

Example: Marek, a field solutions engineer working with clients in Poland, is at a customer site and wants to use an AI tool to translate a technical document from Polish to English for a quick internal review. He is not sure whether the document contains customer data. He decides not to paste the document. Instead, he asks the customer whether the document can be shared with an external tool. When the customer says no, Marek translates the key points manually and sends a summary to his team.

Example: Sofia, a product manager in Fleet Insights, remote from Spain, is drafting a survey for customers about a new feature. She wants to use AI to improve the wording. The survey questions themselves do not contain customer names or data, only generic feature descriptions. Sofia checks the approved tool list, uses the company account, and reviews the final wording before sending it out. That is an appropriate use.

When in doubt, choose the safer path. A few extra minutes of manual work protect our customers, our company, and your own reputation. If you see a colleague about to paste something sensitive into an AI tool, speak up — a friendly reminder helps us all.
