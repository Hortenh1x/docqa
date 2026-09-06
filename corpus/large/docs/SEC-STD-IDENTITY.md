---
doc_id: SEC-STD-IDENTITY
title: Identity & SSO Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Identity & SSO Standard

## 1. Purpose

This standard describes how identity is managed across Kranich Software GmbH. It applies to every employee, contractor, and intern who accesses Kranich Route Cloud, internal tools, or company devices. The goal is simple: one reliable identity for each person, strong verification at sign-in, and sessions that stay safe without getting in the way of work.

Identity management is a shared responsibility. The Platform & Infrastructure team builds and maintains the technical foundation. Information Security sets the rules and monitors for unusual activity. Every individual plays a part by following the practices below and reporting anything suspicious to security@kranich.example.

This standard works together with related policies. For questions about access rights and approvals, see POL-004. For guidance on handling company expenses and travel, see FIN-RATES-2026. Where this document and another policy conflict, the stricter requirement applies.

## 2. SSO

Kranich uses single sign-on (SSO) as the primary way to authenticate to all company applications. SSO means you sign in once and can then reach the tools you need without repeating credentials. This applies to Kranich Route Cloud, Perch, Fern, Ledgerly, Grove, and any other service that supports SSO.

Your SSO account is your corporate identity. It is created when you join and removed promptly when you leave. You must not create separate accounts in company tools for personal convenience. If a tool does not support SSO, request access through it-help@kranich.example and use a unique, strong password stored in 1Password.

You must use your corporate email address for all work-related sign-ins. Personal email addresses are not permitted for company services. This keeps your identity clear and makes it easier to revoke access when needed.

Example: Marek, a field solutions engineer working with clients in Poland, needs to access a customer portal that does not support SSO. He requests a federated account through it-help@kranich.example, stores the credentials in 1Password, and does not reuse his personal accounts.

## 3. Sessions

An SSO session begins when you successfully authenticate and ends when it expires or you sign out. SSO sessions expire after 15 hours. After that, you are prompted to sign in again. This limit applies regardless of whether you are actively working. The purpose is to reduce the window in which an unattended device could be misused.

You should sign out manually whenever you finish work on a shared or borrowed device. Do not leave sessions open on devices you do not control. If you use a personal device for work, enable its screen lock and keep the device with you.

Session behaviour for individual applications may be stricter than the SSO limit. Some tools sign you out after a shorter period of inactivity. Treat those application-level timeouts as the effective rule for that tool.

Example: Deniz, a customer success manager in Berlin, starts her day and signs in through SSO. She steps away for lunch and leaves her laptop locked. When she returns later in the afternoon, her session is still valid because the total time since sign-in is below the limit. If she had worked through a long evening, she would be asked to sign in again after 15 hours.

## 4. MFA

Multi-factor authentication (MFA) is required for every SSO sign-in. MFA combines something you know, such as your password, with something you have, such as an authenticator app on your phone. This second factor protects your account even if your password is compromised.

You must enrol in MFA during onboarding. Use an authenticator app on your personal or company phone. SMS and email codes are not permitted as the primary MFA method because they are less secure. If you cannot use an authenticator app, contact security@kranich.example to discuss an alternative approved method.

Treat MFA prompts with care. If you receive a prompt you did not initiate, do not approve it. Report it to security@kranich.example immediately. This kind of prompt can indicate that someone else is trying to access your account.

You may be asked to verify your identity again with MFA when you perform sensitive actions, even if your session is still active. This is expected and does not mean something is wrong.

Example: Anna, a backend engineer in Lisbon, receives a push notification asking her to approve a sign-in while she is in a meeting. She did not just sign in, so she declines the prompt and reports it to security@kranich.example. Later, she checks with the security team, who confirm that a blocked attempt was made from an unknown location.

## 5. Questions

If you have questions about this standard, contact Information Security at security@kranich.example. For issues with signing in, resetting your MFA device, or accessing a tool, contact it-help@kranich.example.

If you believe your account has been compromised, change your password immediately, revoke your active sessions if you can, and notify security@kranich.example. Do not wait to see if the issue resolves itself.

Suggestions for improving this standard are welcome. Identity and security practices evolve, and we review this document regularly. Share your feedback with your manager or directly with Information Security.

Remember that this standard supports the way we work at Kranich. We are remote-first across Germany, Portugal, Spain, Poland, France, and the United Kingdom. Our identity tools need to work seamlessly from home offices, client sites, and the Ritterstraße and Rua do Alecrim offices alike. Following these rules keeps everyone's data safe while letting us focus on building great route-optimization software for our customers.
