---
doc_id: SEC-RB-OFFB
title: Security Offboarding Runbook
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: confidential
access: Managers only
---

# Security Offboarding Runbook
Access: Managers only

## 1. Purpose

When a colleague leaves Kranich Software, whether by resignation, end of contract, or other circumstances, we must promptly remove their access to company systems and data. This runbook helps managers run a consistent, secure offboarding process. It complements the formal policy in POL-023, which governs access revocation and defines the for-cause revocation window in §4; this runbook does not repeat those rules.

Security offboarding protects client data, internal tools, and the company's reputation. It also protects the departing colleague, who should not be in a position where they could accidentally use stale credentials.

Information Security owns this runbook. Managers execute the steps with support from Platform & Infrastructure and People & Culture. If you are unsure whether a step applies, contact security@kranich.example.

## 2. Checklist

Work through the checklist in order. Mark each item complete before moving to the next. If a step cannot be completed, note the reason and escalate to Information Security.

- Notify Information Security. Send a note to security@kranich.example as soon as you know the departure date. Include the colleague's name, team, and last working day. Do not wait until the final week.

- Confirm the departure date with People & Culture. Lea, in People Operations, will confirm the official last working day and whether any leave is being taken before departure.

- Revoke access to the corporate identity provider. Platform & Infrastructure will disable the account so the colleague cannot sign in to company applications. This includes email, calendar, and single sign-on.

- Disable access to internal tools. The colleague's access to Perch, 1Password, Fern, Ledgerly, and Grove must be removed. If the colleague is a vault owner in 1Password, transfer ownership to another team member first.

- Revoke access to the Kranich Route Cloud production environment. The Routing Core and Fleet Insights teams will remove the colleague from any production roles, service accounts, or shared credentials they held.

- Collect company hardware. Arrange for the return of laptops, monitors, phones, and any other equipment. The Workplace & Operations team, led by Rui, will coordinate logistics. For colleagues in Lisbon, coordinate with the Rua do Alecrim office; for Berlin, the Ritterstraße office.

- Remove physical access. If the colleague worked from an office, revoke their badge or key access. For remote colleagues, confirm they never had physical credentials.

- Transfer files and documents. Ask the colleague to move any client-facing or project files to a shared drive owned by their team. Do not allow them to keep company files in personal storage.

- Change shared passwords. If the colleague knew shared passwords for team mailboxes, vendor portals, or client systems, reset those passwords promptly.

- Communicate internally. The manager should inform the immediate team that the colleague is leaving. Do not share details about the reason for departure beyond what People & Culture has approved.

- Confirm with Information Security. Once all steps are complete, send a confirmation to security@kranich.example. Information Security will close the offboarding ticket.

Example: Deniz, a customer success manager in Berlin, is leaving. Her manager notifies Information Security in good time, confirms the date with Lea, and works with Platform & Infrastructure to disable access. Deniz hands over her client notes to a shared drive before her last day. The team resets the shared mailbox password she used.

## 3. Timing

Begin the offboarding process as soon as you have a confirmed departure date. Do not wait until the colleague's final week. Early notification gives Platform & Infrastructure time to plan access revocation without disrupting the colleague's work in the meantime.

Most steps should be completed by the colleague's last working day. Access to the corporate identity provider and production systems should be revoked promptly on that day, if not before. If the colleague is leaving under circumstances that require immediate action, refer to POL-023 §4 for the for-cause revocation window.

For colleagues on notice period, you may allow them to continue working normally until the revocation date. Do not restrict their access early unless Information Security instructs you to do so.

If the colleague is taking leave before their official departure, coordinate with People & Culture. Access should generally remain active until the last working day, unless the leave is part of a departure arrangement that requires earlier revocation.

Example: Marek, a field solutions engineer working with clients in Poland, resigns with a notice period. His manager starts the checklist immediately, but Marek continues to work with clients until his last day. Access is revoked on that day, and his hardware is returned the following week.

## 4. Questions

If you have questions about this runbook, contact Information Security at security@kranich.example. For questions about the departure process or notice periods, contact People & Culture at people@kranich.example. For hardware collection or office access, contact Workplace & Operations.

If a departing colleague holds a role that requires special attention, such as an engineering manager with broad production access, consult Information Security before starting the checklist. They will advise on additional steps beyond this runbook.

Information Security reviews this runbook regularly and may update it. Managers should check the version in Grove to ensure they are following the current process.
