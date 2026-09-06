---
doc_id: SEC-STD-VENDOR
title: Vendor Security Assessment
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Vendor Security Assessment

## 1. Purpose

Kranich Software GmbH builds trust with our customers by protecting their data. When we share that data with vendors — or when vendors can access our internal systems, networks, or facilities — we need reasonable confidence that they will handle it responsibly.

This standard defines when a vendor security assessment is required, what the assessment covers, and how the questions are scored. It applies to all vendors, subcontractors, and service providers that Kranich engages, regardless of which team initiates the relationship.

The standard is owned by Information Security. Questions about whether an assessment is needed, how to interpret a vendor's answers, or how to handle a vendor that fails the assessment should be directed to security@kranich.example.

## 2. When to assess

Not every vendor needs a full security assessment. A vendor that supplies office plants, for example, never touches our data or systems. A vendor that hosts a customer data export, by contrast, handles sensitive information daily. The effort should scale with the risk.

An assessment is required when any of the following is true:

- The vendor will receive, store, process, or transmit Kranich customer data, including data from the Kranich Route Cloud.
- The vendor will have access to Kranich internal systems, code repositories, or production environments.
- The vendor will access Kranich offices or connect their own devices to the Kranich network.
- The vendor provides services that, if compromised, could disrupt the Kranich Route Cloud or the tools we rely on to run the business.

The team proposing the vendor relationship is responsible for determining whether an assessment is needed. When in doubt, they should ask Information Security before signing anything. It is much easier to assess a vendor before a contract is signed than to retrofit security requirements afterwards.

Example: Marek, a field solutions engineer, wants to bring in a third-party mapping provider to enrich route visualizations for a customer in Poland. The provider would receive anonymized route coordinates. Because that involves customer data, Marek checks with Information Security, and an assessment is scheduled.

If a vendor relationship changes materially — for example, a vendor that previously had no data access now receives a data feed, or a vendor expands its access from development data to production data — a new or updated assessment is required.

## 3. Questionnaire

The assessment is built around a structured questionnaire. The questionnaire is divided into sections that reflect the areas most relevant to how Kranich works with vendors. Each question asks the vendor to describe their practice, and where useful, to provide evidence.

The questionnaire covers the following areas:

- Organisational security: who is responsible for security at the vendor, how security decisions are made, and whether the vendor has a documented security policy.
- Data handling: how the vendor classifies data, what protections apply to data at rest and in transit, and how long data is retained.
- Access control: how the vendor manages user accounts, authentication, and authorisation, and whether access is reviewed periodically.
- Incident response: how the vendor detects, responds to, and communicates security incidents, and whether they have a written incident response plan.
- Subcontracting: whether the vendor uses subprocessors, and if so, how those subprocessors are vetted and contracted.
- Compliance: any certifications, audits, or regulatory frameworks the vendor adheres to.

The questionnaire is sent to the vendor with clear instructions. Vendors are asked to answer each question directly, to provide evidence where requested, and to flag any questions they cannot answer. A vendor that skips questions without explanation will be asked to complete them before the assessment can proceed.

Example: Deniz, a customer success manager, proposes a vendor that will host a customer-facing portal. Information Security sends the questionnaire to the vendor's security contact. The vendor completes it within a few days and provides their audit report as evidence.

## 4. Questions

The questions below form the core of the assessment. They are not a checklist to be answered yes or no; the vendor's written responses are reviewed in context, and follow-up questions are common.

**Organisational security**

- Does the vendor have a named person or team responsible for information security? Who is it, and how can they be reached?
- Does the vendor maintain a written information security policy? When was it last reviewed, and who approves changes?
- How does the vendor ensure that security responsibilities are understood by employees and contractors?

**Data handling**

- What categories of data will the vendor receive from or on behalf of Kranich?
- How is data protected while in transit and while at rest? What encryption standards are used?
- For how long is data retained, and how is it deleted when no longer needed?
- Is any of the data stored or processed outside the country where Kranich operates? If so, where?

**Access control**

- How are user accounts created, modified, and removed? Is there a formal process for offboarding?
- Does the vendor require multi-factor authentication for access to systems that store or process Kranich data?
- How are user permissions reviewed, and how often?
- Are vendor employees granted access on a least-privilege basis?

**Incident response**

- Does the vendor have a written incident response plan? What does it cover?
- How does the vendor detect security incidents, and who is on call?
- How and when would the vendor notify Kranich of a security incident that affects Kranich data or systems?
- Does the vendor conduct post-incident reviews, and are lessons learned shared with customers?

**Subcontracting**

- Does the vendor use subcontractors or subprocessors to deliver the services to Kranich?
- How are subcontractors selected and assessed?
- What contractual protections apply to data shared with subcontractors?

**Compliance**

- What security certifications, audits, or assessments does the vendor hold?
- Has the vendor experienced any security incidents in the past few years that involved customer data? If so, what happened and what changed?
- Does the vendor have cyber insurance? If so, what does the policy cover?

**Scoring and outcome**

Each answer is reviewed by Information Security and scored as acceptable, acceptable with conditions, or unacceptable. The overall outcome is determined by the lowest score across all sections — a vendor that answers well everywhere but poorly on incident response still represents a risk.

An acceptable outcome means the vendor can be engaged without further security work. An acceptable-with-conditions outcome means the vendor can be engaged, but the conditions must be written into the contract and tracked. An unacceptable outcome means the vendor should not be engaged, or the engagement should be redesigned so that the risky activity is removed.

Example: Anna, a backend engineer in Lisbon, proposes a vendor that will provide a code-scanning service. The vendor's answers are strong on access control and data handling, but their incident response plan does not mention customer notification. Information Security marks the outcome as acceptable with conditions: the vendor must commit to notifying Kranich within a defined period after discovering a relevant incident, and the commitment must appear in the contract.

The results of the assessment are shared with the team that proposed the vendor, and a summary is stored in the vendor register. The full questionnaire and the vendor's responses are kept by Information Security. Reassessments are scheduled based on the risk level of the relationship; a vendor handling sensitive customer data is reviewed more frequently than a vendor with no data access.

Where a contract is needed, the assessment outcome informs the security terms. Vendors that receive an acceptable-with-conditions outcome must have those conditions reflected in the agreement. For guidance on contract terms, refer to the procurement policy and the information security policy, POL-004. For matters related to how data is rated or handled, refer to the data classification standard.

Questions about this standard, the questionnaire, or a specific vendor should be sent to security@kranich.example. The team is happy to help early in the process, before a vendor is selected or a contract is drafted.
