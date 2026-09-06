---
doc_id: SEC-STD-CLOUD
title: Cloud Security Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Cloud Security Standard

## 1. Purpose

Kranich Route Cloud is built on cloud infrastructure. This standard defines the baseline security requirements for every cloud account, network, and secret that supports our product and internal operations. It applies to all employees, contractors, and tools that touch our cloud environment, regardless of where they work.

We keep this standard short and practical. If you ever face a situation where following a rule here would make our customers' data less safe, stop and contact security@kranich.example before proceeding. When in doubt, ask.

Example: Anna, a backend engineer in Lisbon, wants to spin up a new service. She reads this standard before creating the cloud resource, so she knows which account to use and how to store the service's credentials.

## 2. Accounts

### 2.1 Cloud accounts

We maintain separate cloud accounts for production, staging, and development. Never run production workloads in a development account, and never use a production account for experiments. If you need a new account, ask your engineering manager, who will coordinate with Platform & Infrastructure.

Each cloud account has a designated owner. The owner is responsible for reviewing access quarterly and for ensuring the account's purpose is documented in Grove.

### 2.2 Human access

Access to cloud accounts is granted through our identity provider. Every human user must have a unique account; shared or generic logins are not permitted. When you join a new team or change roles, your access must be reviewed and updated promptly.

Access is granted on a least-privilege basis. Start with the minimum permissions you need, and request more only when your work requires it. Platform & Infrastructure reviews access rights regularly and may revoke permissions that are no longer justified.

Example: Marek, a field solutions engineer, needs read-only access to a production account to help a customer troubleshoot. His manager approves the request, and Platform & Infrastructure grants only the specific read permission needed — not broader write access.

### 2.3 Service accounts

Service accounts must be named clearly to indicate their purpose and owner. Each service account must have a documented owner in the team's repository. When a service account is no longer needed, delete it.

Service account credentials must be stored in our secrets manager, never in code or configuration files. See §4 for details.

### 2.4 Offboarding

When you leave Kranich or change to a role that no longer requires cloud access, your accounts are deactivated as part of the standard offboarding process coordinated by People & Culture. If you know that a colleague has left or changed roles and still has cloud access, report it to it-help@kranich.example.

## 3. Network

### 3.1 Network segmentation

Production resources must reside in their own virtual network, isolated from development and staging networks. Within the production network, separate subnets separate tiers — for example, the application tier and the data tier. Traffic between tiers is allowed only where necessary for the product to function.

Platform & Infrastructure maintains the reference architecture for network segmentation. If your service does not fit the reference architecture, discuss it with Platform & Infrastructure before you build it.

### 3.2 Inbound access

All inbound traffic to production must pass through our managed ingress layer. Do not expose services directly to the internet with a public IP address unless Platform & Infrastructure has explicitly approved an exception.

Remote access to internal networks must use our corporate VPN. You must not create alternative tunnels, port forwards, or jump hosts that bypass the VPN.

Example: Deniz, a customer success manager in Berlin, sometimes needs to reach a staging environment to verify a fix. She connects through the corporate VPN rather than asking an engineer to open a direct route from her laptop.

### 3.3 Outbound access

Production services should not initiate outbound connections to the public internet unless required. Where outbound access is needed, restrict it to the specific destinations the service requires. Use allow-lists rather than broad rules.

### 3.4 Encryption in transit

All traffic between our services must be encrypted in transit. Use TLS for HTTP-based traffic and the equivalent encryption for other protocols. Do not disable certificate verification or use weak cipher suites.

Traffic between our cloud environment and customer integrations must also be encrypted. If a customer requests an unencrypted integration, refer them to the Customer Success team, who will coordinate with Information Security.

### 3.5 Monitoring

Network traffic is monitored for anomalies. Platform & Infrastructure operates the monitoring tooling, and Information Security reviews alerts. If you notice unusual network behavior — unexpected connections, slow responses, or unfamiliar IP addresses in logs — report it to security@kranich.example.

## 4. Secrets

### 4.1 What counts as a secret

A secret is any credential or piece of sensitive data that grants access to our systems. Examples include API keys, database passwords, service account tokens, and encryption keys. If you are unsure whether something is a secret, treat it as one.

### 4.2 Storing secrets

All secrets must be stored in our approved secrets manager. Do not store secrets in source code, configuration files, environment variables in plain text, documentation, or chat messages. Do not commit secrets to a repository, even temporarily.

If you need a secret for local development, retrieve it from the secrets manager and store it in your local secrets store. Never paste a secret into a shared document or a support ticket.

Example: Sofia, a product manager in Spain, needs an API key to test a new Fleet Insights feature. She asks an engineer to grant her access to the secret in the secrets manager rather than having the engineer send the key over chat.

### 4.3 Rotating secrets

Secrets must be rotated on a regular schedule, and immediately when they may have been compromised. If you suspect a secret has leaked — for example, if it appeared in a log or was sent to the wrong person — rotate it right away and inform Information Security.

Automated rotation is preferred. When you create a new secret, configure automated rotation where the service supports it. For secrets that require manual rotation, set a reminder in your calendar or team tooling.

### 4.4 Access to secrets

Access to secrets is granted on a need-to-know basis. Before requesting access, consider whether you truly need the secret to do your work. Secrets manager access is logged, and Information Security reviews the logs periodically.

Never share a secret with someone who does not have explicit access. If a colleague asks you for a secret, point them to the secrets manager and suggest they request access through the standard process.

### 4.5 Secrets in code

When writing code that interacts with secrets, use the SDK or client library provided by our secrets manager. Do not hardcode fallback values or default credentials. If you find a hardcoded secret in code, remove it immediately and rotate the secret.

### 4.6 Incident response

If a secret is compromised, follow the incident response process described in the Information Security policy library. At minimum, rotate the secret, assess what the compromised secret could have accessed, and document what happened. Do not wait for permission to rotate a secret that may be compromised — act first, then inform.

## 5. Questions

If you have questions about this standard, or if you encounter a situation that is not covered here, contact Information Security at security@kranich.example.

For practical help with cloud accounts, network configuration, or the secrets manager, contact Platform & Infrastructure at it-help@kranich.example.

For questions about access reviews or offboarding, contact People & Culture at people@kranich.example.

We review this standard at least once a year. If you have suggestions for improvement, share them with Information Security — we welcome input from every team.

Example: Lea, a people operations specialist in Berlin, is helping a new engineer through onboarding. She is unsure whether the new hire needs cloud access on day one. She checks with the engineering manager and Platform & Infrastructure, who confirm that access is granted after the initial security briefing, not before. Lea documents this in the onboarding checklist in Grove so future hires have a clear path.

This standard works together with our other security policies. Refer to the policy library in Grove for related documents, including the access management policy and the incident response plan. Where this standard and another policy appear to conflict, contact Information Security for guidance before acting.

Thank you for keeping Kranich Route Cloud secure. Every account you create, every network you configure, and every secret you handle is part of protecting our customers' data. Your care matters.
