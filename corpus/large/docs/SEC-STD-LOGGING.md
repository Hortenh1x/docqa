---
doc_id: SEC-STD-LOGGING
title: Logging & Monitoring Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Logging & Monitoring Standard

## 1. Purpose

Kranich Route Cloud processes sensitive customer data for logistics operators across Europe. To protect that data and to keep our platform reliable, we need to know what is happening inside our systems. This standard explains what we log, how long we keep those logs, and how we turn log data into alerts that help us respond to problems early.

Logging and monitoring serve three purposes. First, they help us detect security incidents such as unauthorized access or suspicious behavior. Second, they help us diagnose technical issues and keep the platform available for our customers. Third, they help us meet our contractual and regulatory obligations.

This standard applies to all Kranich Software employees and contractors who build, operate, or maintain systems that are part of the Kranich Route Cloud production environment. It also applies to internal systems that store customer data or credentials. The Head of Information Security owns this standard and reviews it at least once per year.

We aim to log enough to answer the question "what happened, when, and who did it" — but no more than necessary. Over-logging creates noise and privacy risk. Under-logging leaves us blind. This standard describes the balance we strike.

## 2. What we log

We log events from three layers: the application layer, the infrastructure layer, and the security layer. Each layer has a defined set of event types that must be captured.

**Application layer.** The Routing Core, Fleet Insights, and Platform & Infrastructure teams must log the following events from the services they own:

- Authentication events, including successful and failed login attempts, password resets, and session creation or termination.
- Authorization decisions, particularly when a user is granted or denied access to a resource they requested.
- Data changes that are material, such as creating, updating, or deleting a customer account, a route plan, or a configuration setting.
- Errors and exceptions that indicate a malfunction, including timeouts, failed integrations, and unexpected input.
- Outbound calls to third-party services, including the service name and the outcome of the call.

**Infrastructure layer.** The Platform & Infrastructure team must ensure that the following are logged for every component in the production environment:

- Server startup and shutdown events.
- Network connections to and from production components, including source and destination addresses.
- Resource exhaustion events, such as a service running out of memory or disk space.
- Configuration changes made to infrastructure, including who made the change and when.
- Deployment events, including which version of a service was deployed and by whom.

**Security layer.** The Information Security team defines a set of security-specific logs that must be collected from all layers. These include:

- Access to secrets and credentials stored in 1Password, including the user and the item accessed.
- Changes to access control lists and role definitions.
- Attempts to access resources outside of normal patterns, such as repeated failed logins or access from unusual locations.
- Activity in the internal tools Perch, Fern, Ledgerly, and Grove that involves sensitive personal data.

**What we do not log.** We do not log the contents of requests or responses where those contents include customer route data, personal data of end customers, or payment information. We do not log passwords, tokens, or other secrets in plain text. We do not log full email bodies or chat messages. When an event requires context that includes sensitive data, we log a reference to the data — such as an identifier — rather than the data itself.

**Correlation identifiers.** Every log entry must include a correlation identifier that ties it to a single user request or background job. This allows us to reconstruct a complete sequence of events across services. The identifier must be generated at the entry point of the request and propagated through all downstream calls.

**Time and source.** Every log entry must include a timestamp in UTC and the name of the service or component that produced the entry. The timestamp must be accurate to the second. The team responsible for a service must ensure that the system clock on the host is synchronized with a reliable time source.

**Format.** Log entries must be written in a structured format, such as JSON, so that they can be searched and aggregated automatically. Free-text log messages are allowed as a human-readable field, but the machine-readable fields must carry the structured data.

Example: Anna, a backend engineer in Lisbon, adds a new endpoint to the Routing Core service. Before she merges her code, she checks the logging guidelines for the service and adds structured log statements for authentication checks and for any data change the endpoint performs. She also includes the correlation identifier from the incoming request in every log line she writes.

Example: Deniz, a customer success manager in Berlin, contacts IT support because a customer reported a problem with their route plan. The support engineer uses the correlation identifier from the customer's session to trace the request through the Routing Core and Fleet Insights services and identifies the failing component within a few minutes.

## 3. Retention

Different types of logs have different retention periods. We keep security logs for 230 days. This period is long enough to support incident investigations and to comply with our contractual obligations to customers.

Application and infrastructure logs that are not classified as security logs are kept for a shorter period, which is defined in the operational runbooks for each service. Logs that contain personal data of our employees — such as authentication logs for internal tools — are subject to the data protection principles in our employee privacy policy and are only accessible to the people who need them for their role.

At the end of the retention period, logs must be deleted automatically. Manual deletion is acceptable only when automatic deletion is technically impossible, and in that case the team responsible must document the reason and delete the logs promptly. Logs that are part of an active incident investigation or a legal hold must be preserved until the investigation or hold is concluded, regardless of the normal retention period.

Logs are stored in a central logging platform operated by the Platform & Infrastructure team. Access to this platform is restricted to employees who need it for their role. Access is granted through the normal access request process and reviewed periodically by the Head of Information Security.

Example: Marek, a field solutions engineer working with clients in Poland, needs to investigate a customer issue that occurred a few weeks ago. He requests access to the central logging platform. His manager approves the request, and the Platform & Infrastructure team grants him read-only access. He finds the relevant log entries and resolves the issue. His access is reviewed at the next quarterly access review.

## 4. Alerting

Logging is only useful if someone — or something — acts on the data. We define alerts for events that require a response. Alerts are configured in the monitoring system and are routed to the team that owns the affected service.

**Alert tiers.** Alerts are classified into three tiers:

- **Critical.** The event indicates a security incident or a complete loss of service. Critical alerts are sent to the on-call engineer and to the Head of Information Security. The on-call engineer must respond immediately.
- **Warning.** The event indicates a potential problem that does not yet require immediate action. Warning alerts are sent to the owning team's channel. A team member must acknowledge the alert during business hours and investigate.
- **Informational.** The event is notable but does not require action. Informational alerts are logged and reviewed periodically.

**Required alerts.** The following alerts must be configured for all production services:

- A single authentication failure that occurs for an account that is known to be a service account.
- A series of authentication failures for the same user account within a short window.
- An authentication success that follows a series of failures for the same account.
- A change to a production configuration that is made outside of the approved change window.
- A deployment that fails or that is rolled back.
- A service that is down or unresponsive for longer than the health check interval.
- A log volume that drops to zero for a service that should be producing logs.

**Alert content.** Every alert must include the service name, the environment, the correlation identifier of the triggering event if available, and a short description of what happened. Alerts must not include sensitive data such as passwords or customer route data.

**Response.** Teams must document a response procedure for each alert they own. The procedure must state who is responsible for responding, what steps to take to investigate, and when to escalate to the Head of Information Security. If an alert fires and the investigation reveals a potential security incident, the engineer must follow the incident response process defined in the security incident policy.

**Testing.** Alerting rules must be tested when they are created and whenever the underlying service changes in a way that could affect the alert. The Platform & Infrastructure team runs a regular test of the alerting pipeline to ensure that alerts are delivered reliably.

**Reducing noise.** An alert that fires repeatedly without requiring action is a sign that the alert rule is too broad. Teams should review their alert rules periodically and tune them to reduce noise. A noisy alert that is ignored is worse than no alert at all, because it trains people to disregard warnings.

Example: Sofia, a product manager in Fleet Insights, is on call for her team during a release week. A warning alert fires because the new release is producing a higher rate of errors than the previous version. Sofia investigates, finds a misconfigured setting in the new version, and rolls back the deployment. She documents the issue in the team's channel so the engineer who owns the configuration can fix it before the next release.

## 5. Questions

If you have questions about this standard, or if you believe you have found a gap in our logging coverage, please reach out.

- For questions about logging in a specific service, contact the team that owns the service.
- For questions about access to logs or the central logging platform, contact it-help@kranich.example.
- For questions about security log requirements, incident response, or this standard, contact security@kranich.example.

If you notice that a system is not producing logs, or that logs are missing for an event that should have been captured, report it promptly to the Platform & Infrastructure team and to security@kranich.example. Early detection of a logging gap can prevent a small problem from becoming a major incident.

This standard is part of our broader security framework. It complements the access control policy and the incident response policy. When you are unsure which policy applies, err on the side of logging more and asking questions early — but remember that logging more means storing more personal data, so always apply the principle of least privilege to log content as well as to log access.

We review this standard annually. If you have suggestions for improvement, we welcome them. Good logging practices make Kranich Route Cloud safer for our customers and more pleasant to operate for all of us.
