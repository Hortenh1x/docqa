---
doc_id: SEC-STD-ENDPOINT
title: Endpoint Security Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Endpoint Security Standard

## 1. Purpose

This standard defines how we protect the laptops, desktops, and other company-managed devices that we use to do our work. Kranich Software GmbH is a remote-first company, and our endpoints are the primary gateway to the Kranich Route Cloud, our customer data, and our internal tools. A well-configured endpoint is the first line of defense against malware, phishing, and unauthorized access.

This standard applies to all company-issued devices and to any personal device that is used to access company resources, where such access is permitted under the relevant policy. It covers the baseline security configuration, disk encryption, and patching expectations for every device. The standard is written for everyone at Kranich — engineers, customer success managers, people operations, and leadership alike — and it is meant to be practical, not burdensome.

If you have questions about how this standard applies to your specific device or work pattern, reach out to security@kranich.example. For day-to-day technical issues with your device, contact it-help@kranich.example. For anything related to your working arrangements or equipment, people@kranich.example can point you in the right direction.

## 2. Baseline

Every device that Kranich issues — whether a laptop, a desktop, or a mobile device — must be enrolled in our device management solution before it is used for work. Enrollment happens as part of the onboarding process, and it ensures that the device receives our standard security configuration, can be located if lost, and can be remotely wiped if necessary.

The baseline configuration for all company-managed endpoints includes the following requirements:

- A strong device password or biometric authentication must be enabled. Screen lock must engage automatically after a short period of inactivity.
- Full disk encryption must be active, as described in §3 of this standard.
- Automatic updates must be enabled for the operating system and for all approved software.
- Firewall software must be turned on and configured to block unsolicited inbound connections.
- Company-approved antivirus or endpoint detection and response software must be installed and running.
- Browsers must be configured to block pop-ups and to warn against unsafe downloads.
- Administrative (root or administrator) access on the device must be limited to what your role genuinely requires. If you need administrator rights for development or testing, request them through it-help@kranich.example, and they will be granted on a case-by-case basis.

Example: Marek, a field solutions engineer who works with clients in Poland, receives a new laptop before an on-site workshop. During onboarding, the device is enrolled, encrypted, and configured with the standard firewall and antivirus settings. When he later needs to install a specialized network diagnostic tool for a client demonstration, he requests administrator access through it-help, which is granted for a limited purpose and then reviewed.

Personal devices are not a substitute for company-managed hardware when company data is involved. If you occasionally need to check email or calendar from a personal phone, that is acceptable provided the device has a passcode and the latest operating system. However, personal devices must never be used to store customer data or to access the Kranich Route Cloud production environment. If you are unsure whether a particular task is appropriate for a personal device, ask your manager or security@kranich.example before proceeding.

Lost or stolen devices must be reported to it-help@kranich.example immediately. The sooner we know, the sooner we can remotely lock or wipe the device to protect company and customer information. Do not attempt to track or retrieve a lost device on your own if it contains sensitive data — let the security team handle it.

## 3. Encryption

Full disk encryption is mandatory on every company-managed laptop and desktop. This requirement is non-negotiable because our devices travel with us — between home offices, client sites, and the Kranich offices in Berlin and Lisbon — and a device without encryption exposes all data on it if it falls into the wrong hands.

Encryption must be native, hardware-backed, and enabled before the device is used for any work purpose. For laptops and desktops, we use the operating system's built-in full disk encryption capability. Mobile devices must have their storage encrypted as well, which is typically enabled by default when a passcode is set.

The encryption key must be escrowed with our device management solution so that we can recover data in the event of a forgotten password or a departing employee. Do not disable encryption, do not remove the escrow, and do not store encryption recovery keys in unsecured notes or documents.

Example: Anna, a backend engineer in Lisbon, works from the Rua do Alecrim office and from home. Her laptop is encrypted with a hardware-backed key that is escrowed automatically. When she forgets her login password after a long holiday, the it-help team uses the escrowed key to help her regain access without losing any local work. Because encryption was active, she never had to worry about the data on her device being exposed during the recovery process.

If you connect an external drive or USB stick to a company device, it must be encrypted as well. Removable media often contains copies of code, documents, or customer data, and unencrypted media is a common source of data leakage. Encrypt any removable media before writing company information to it, and never use unencrypted media to transport customer data between locations.

Cloud storage is not a substitute for device encryption — it is complementary. Files stored in the Kranich Route Cloud or in our approved collaboration tools are protected by our cloud security controls, but the local copies on your device are protected by this standard. Both layers matter.

## 4. Patching

Keeping software up to date is one of the most effective ways to protect against known vulnerabilities. This standard sets clear expectations for how quickly patches must be applied, and it applies to the operating system, browsers, productivity software, development tools, and any other software installed on company-managed devices.

Critical patches are installed within 12 calendar days of release. This applies to patches that address vulnerabilities with a known exploit or that are rated critical by the software vendor. Our device management tool tracks patch status centrally, and it-help monitors compliance. If a critical patch cannot be applied within the required window — for example, because of a compatibility issue with a specialized tool — you must notify it-help promptly so they can track the exception and apply a compensating control.

For non-critical patches, including routine operating system updates and feature releases, we expect them to be installed as soon as they are available, and no later than the next scheduled maintenance window. Automatic updates should remain enabled at all times. If you see a prompt to restart your device to complete an update, do not postpone it indefinitely — a restart takes only a few minutes and closes the window of exposure.

Example: Deniz, a customer success manager in Berlin, receives a notification that a critical security patch is available for her laptop's operating system. She is in the middle of a customer call, so she dismisses the reminder and continues working. Later that day, she sees a second reminder from the device management tool and restarts her laptop during her lunch break. The patch is installed well within the 12 calendar days window, and Deniz has not put any customer data at risk.

Software that is no longer supported by its vendor — sometimes called end-of-life software — must not be installed on company devices. Unsupported software does not receive patches, which means it can never meet the requirements of this standard. If you need a piece of software that is no longer supported, discuss alternatives with your manager and it-help. In rare cases, an exception may be granted for a specific business need, but the exception must be documented and must include compensating controls.

Patching applies to all devices, regardless of where you work. Whether you are at home in Spain, in a client office in Poland, or at the Ritterstraße office in Berlin, the same patching expectations apply. The device management solution works over the internet, so being remote is not a reason to delay updates.

## 5. Questions

If you have questions about this standard, start with your manager or with the it-help alias. For security-specific concerns — such as whether a particular action is allowed, how to handle a suspected compromise, or how this standard interacts with other security policies — contact security@kranich.example. We are happy to explain the reasoning behind any requirement and to help you find a secure way to do your work.

This standard is part of our broader security framework. Related requirements are described in POL-004, which covers information security roles and responsibilities, and in the financial systems standard FIN-RATES-2026, which applies to devices used for expense and travel processing. When in doubt, the security team is here to help — no question is too small.

Example: Lea, a people operations specialist in Berlin, is preparing to onboard a new colleague who will be based in France. She is unsure whether the new hire's device will need any additional configuration because they will be working across borders. She writes to security@kranich.example with her question, and the team confirms that the standard endpoint configuration applies uniformly, with no country-specific exceptions. Lea passes this information along to the new hire, and the onboarding proceeds smoothly.

Thank you for doing your part to keep Kranich — and our customers — secure.
