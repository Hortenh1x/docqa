---
doc_id: SEC-STD-DATACLASS
title: Data Classification Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Data Classification Standard

## 1. Purpose

Kranich Software GmbH handles a wide range of data in its daily operations: customer account information, routing algorithms, employee records, and internal communications. Not all data carries the same sensitivity. Some information, if exposed, could harm our customers, our employees, or our business. Other information is meant to be shared freely.

This standard defines a simple classification scheme for all data that Kranich creates, receives, or stores. It explains what each class means and how you should handle data in each class. Following this standard helps us protect what matters, share what should be shared, and comply with our obligations under applicable law and customer contracts.

This standard applies to all employees, contractors, and anyone else who accesses Kranich systems or data. It covers data in all forms: documents, emails, chat messages, source code, configuration files, databases, and spoken conversations that involve business information.

If you are ever unsure which class applies, choose the more restrictive class and ask your manager or the Information Security team. You can reach us at security@kranich.example.

## 2. Classes

We use four classes. Each class has a name, a description, and examples of typical data that falls into it.

### Public

Public data is information that Kranich has intentionally released for anyone to see. It requires no special protection. Public data includes marketing materials, press releases, the company website, and public product documentation. You may share public data freely with anyone, both inside and outside Kranich.

Example: Deniz, a customer success manager in Berlin, shares a link to our public help center with a prospective customer. The help center articles are public data, so no approval is needed.

### Internal

Internal data is information that is not public but is not sensitive enough to require special protection. It is meant for use within Kranich. Internal data includes most internal announcements, general project documentation, org charts, internal meeting notes, and non-confidential code that is not part of a customer deliverable. You may share internal data with any Kranich employee or contractor. You may share it with outsiders only when the recipient has a legitimate need, such as a vendor under a non-disclosure agreement, and when your manager approves.

Example: Lea, a people operations specialist in Berlin, shares the new office layout plan with the Workplace team. The plan is internal data; it is not public, but it does not contain personal or financial details.

### Confidential

Confidential data is information that could harm Kranich, its customers, or its partners if disclosed. This class includes customer contracts, customer account details, pricing information, sales forecasts, internal financial reports, source code for our core routing engine, and security-related documentation. Confidential data also includes personal data of employees and customers, such as home addresses, bank account numbers, and performance reviews.

You may access confidential data only when your role requires it. You may share confidential data only with Kranich employees who have a legitimate need to know, and with external parties only when a signed non-disclosure agreement is in place and your manager or the Information Security team has approved the sharing.

Example: Marek, a field solutions engineer working with clients in Poland, receives a draft contract from a customer. The contract contains pricing terms and service levels. Marek stores it in the approved customer folder and does not forward it to anyone outside the deal team.

### Restricted

Restricted data is the most sensitive class. It includes authentication credentials, private keys, production database passwords, and access tokens. It also includes data that is subject to strict legal or contractual obligations, such as certain health-related data or payment card data that falls under industry standards.

Restricted data may be accessed only by named individuals whose job requires it. It must be stored only in approved systems, such as our password manager or the designated secrets vault. You may never share restricted data through email, chat, or any other unapproved channel. You may never copy restricted data to personal devices or personal cloud storage.

Example: Anna, a backend engineer in Lisbon, needs a production database password to troubleshoot an incident. She retrieves it from the approved secrets vault using her own authenticated session. She does not write the password into a chat message or a code comment.

If you are unsure whether something is confidential or restricted, treat it as restricted and ask the Information Security team.

## 3. Handling rules

The rules below describe how to handle data in each class across common activities: storage, transmission, access, retention, and destruction. When in doubt, apply the stricter rule.

### Storage

Store public and internal data in the approved collaboration tools, such as Grove or the shared drives. Store confidential data only in systems that support access control, such as the customer relationship management tool or the approved document repository. Store restricted data only in the designated secrets vault or another system that the Information Security team has explicitly approved.

Never store confidential or restricted data on personal devices, personal email accounts, or unapproved cloud services. If you must work with such data on a laptop, ensure the laptop is managed by Kranich and protected by full-disk encryption.

Example: Sofia, a product manager working remotely from Spain, writes a product requirements document that includes customer interview notes. The notes contain customer names and business details, so Sofia saves the document in the approved project repository rather than in a personal notes app.

### Transmission

You may send public data through any channel. You may send internal data through standard Kranich channels, including email and chat. For confidential data, use only the approved file-sharing or email systems, and consider whether encryption is required. For restricted data, do not transmit it through email or chat at all. Use the approved mechanism, such as the secrets vault or a secure transfer tool, and confirm the recipient before sending.

If you receive confidential or restricted data through an unapproved channel, do not open attachments or follow links. Notify security@kranich.example promptly.

### Access

Access to data must follow the principle of least privilege. Give people access only to the data they need for their current role. When someone changes teams or leaves Kranich, revoke or adjust their access promptly. Use the access review process that the Platform & Infrastructure team runs.

Never share your login credentials with anyone. Use 1Password to store your passwords and never reuse a password across systems. If you suspect that your credentials have been compromised, change them immediately and report the incident to security@kranich.example.

Example: Ines Duarte, an engineering manager in Berlin, welcomes a new member to the Routing Core team. She requests access to the routing repository for the new hire and verifies that the departing team member's access has been removed.

### Retention and destruction

Keep data only as long as you need it for a legitimate business purpose. Follow the retention schedules defined in the relevant policies, such as POL-004 for personnel records. When data is no longer needed, delete it using the approved method. For paper documents that contain confidential or restricted data, shred them rather than discarding them in the regular trash.

When you leave Kranich or change roles, return or destroy any confidential or restricted data that you no longer need. If you are unsure whether you may keep a document, ask your manager.

### Labeling

Label documents and emails with their classification when practical. Use the classification labels that the Information Security team has configured in our tools. For documents, add the class name in the header or footer. For emails, add the class to the subject line when the content is confidential or restricted.

Labeling is not required for every internal chat message, but you should label any message that contains confidential data so that recipients understand the sensitivity.

### Incidents

If you believe that confidential or restricted data has been exposed to an unauthorized person, report it immediately. Do not attempt to investigate or fix the issue on your own. Send a message to security@kranich.example with as much detail as you can: what data was involved, when you noticed the issue, and who might have seen it. The Information Security team will guide the response.

Example: Deniz accidentally attaches a customer contract to an email and sends it to the wrong external recipient. She notices the error immediately. She does not send a follow-up email to the wrong recipient. Instead, she reports the incident to security@kranich.example and waits for instructions.

## 4. Questions

If you have questions about how to classify a specific piece of data, or how to handle data in a particular situation, ask your manager first. They can often resolve the question quickly. For deeper questions about classification, access, or security requirements, contact the Information Security team at security@kranich.example.

For questions about data protection obligations under applicable law, or about the data processing agreements we have with customers, contact the legal contact within the company. For questions about employee personal data, contact people@kranich.example.

You can also find related guidance in the policy library on Grove. Relevant documents include POL-004, which covers personnel records, and the access management standard maintained by Platform & Infrastructure. Remember that this standard works together with those documents. Where a conflict appears, the stricter rule applies.

Thank you for taking the time to read this standard. Data classification is everyone's responsibility, and your care makes a real difference in keeping Kranich, our customers, and our colleagues safe.
