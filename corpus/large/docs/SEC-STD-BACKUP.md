---
doc_id: SEC-STD-BACKUP
title: Backup Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Backup Standard

## 1. Purpose

Kranich Software builds route-optimization software that our customers rely on every day. The Kranich Route Cloud holds customer data, configuration, and the code that keeps our service running. If we lose that data, we lose trust. This standard explains how we protect our data by backing it up, how long we keep backups, and how we make sure those backups actually work when we need them.

This standard applies to all systems and services that store company or customer data, whether they run in our own infrastructure or in a cloud provider. It covers production databases, object storage, configuration stores, and the internal tools we use to run the company. It does not cover individual laptop files; for your device, please follow the guidance in POL-004 about endpoint protection and data handling.

The goal is simple: in the event of an outage, an accidental deletion, or a malicious attack, we can restore our systems to a recent, known-good state. We accept that no backup strategy is perfect. We design ours so that the most important data is recoverable within a reasonable time, and so that we regularly prove that recovery works.

## 2. What is backed up

We back up anything that would be painful or impossible to recreate. The list below describes the main categories, but it is not exhaustive. If you are unsure whether a system needs a backup, ask the Platform & Infrastructure team.

**Production data.** All databases that support the Kranich Route Cloud are backed up. This includes the routing engine's state, customer account information, and operational metrics. The Routing Core and Fleet Insights teams own the services that write this data; the Platform & Infrastructure team owns the backup pipelines.

**Object storage.** Customer-uploaded files, such as fleet manifests and geodata, live in object storage. We back up these buckets to a separate storage location so that an accidental deletion or a regional failure does not destroy them.

**Configuration and infrastructure as code.** Our infrastructure is defined in code and stored in version control. Version control history acts as a backup for configuration. We also back up the state files that track our deployed infrastructure, because losing those would make it harder to recover our environment.

**Internal tools.** The tools we use to run the company — our HRIS Fern, the expense system Ledgerly, the password manager 1Password, and the intranet Grove — are mostly software as a service. We rely on the vendors for their own backups, but we also export critical data from these tools on a regular schedule where the vendor supports it. For example, we export the org chart and leave data from Fern, and we keep a copy of our policy library from Grove. This protects us if a vendor has an outage or if we need to change providers.

**Code repositories.** Our source code is backed up through the version control system, including all branches and tags. We do not take separate snapshots of code repositories, because the version control history is sufficient for recovery.

**Not backed up.** We do not back up local files on laptops or workstations. We do not back up temporary files, caches, or build artifacts that can be regenerated. We do not back up personal files that employees store on company devices.

Example: Anna, a backend engineer in Lisbon, stores a local copy of a routing experiment on her laptop. She loses the file when her laptop fails. That file is not backed up under this standard, but the code she wrote for the experiment is in the repository, and the data she used is in the production database. She can recreate the experiment.

## 3. Retention

Backups are retained for 105 days. This retention period applies to all backups taken under this standard, from the moment the backup is created. After the retention period ends, the backup is deleted automatically. We do not keep backups longer than the retention period unless a legal hold requires us to do so, in which case the Information Security team coordinates with the relevant teams.

The retention period balances two needs. On the one hand, we want to be able to recover data from a few weeks or a few months ago, for example if a bug corrupts data slowly over time and we only notice later. On the other hand, keeping backups forever increases cost and creates a larger attack surface: an attacker who compromises our backup storage would have access to a long history of data. A retention period of 105 days gives us a reasonable window for recovery without holding data indefinitely.

We take a new backup on a regular basis. The exact frequency depends on the system and is defined by the Platform & Infrastructure team in the system design documents. Some systems are backed up several times a day, others once a day. The retention period applies to every backup, so we always have a rolling window of the last 105 days.

Example: Deniz, a customer success manager in Berlin, accidentally deletes a customer's configuration while testing a new workflow. The customer notices two weeks later. Because the backup retention period is 105 days, the Platform & Infrastructure team can restore the configuration from a backup taken before the deletion. If the deletion had happened several months ago, the backup would no longer exist, and Deniz would need to recreate the configuration from other sources.

Backup deletion is automated. We do not rely on someone remembering to delete old backups. The backup system marks each backup with its creation date and deletes it once the retention period has passed. If a backup cannot be deleted because of a technical issue, the Platform & Infrastructure team investigates promptly.

## 4. Restore tests

A backup that has never been restored is not a backup — it is a hope. We test our backups regularly to make sure they work. A restore test means taking a backup and actually recovering the data from it into a test environment, then verifying that the data is complete and usable.

**Schedule.** We test restores on a regular schedule. The Platform & Infrastructure team owns the schedule and publishes it internally. At a minimum, each production database is restored and verified at least once every few months. Object storage buckets are tested on a similar cadence. We test the most important systems more often than the less critical ones.

**What a test covers.** A restore test verifies three things. First, that the backup file is readable and not corrupted. Second, that the data inside the backup is complete — for a database, that means the tables and rows are present; for object storage, that means the files are there. Third, that the restored data can actually be used by the application. For a database, this means starting the application against the restored database and running a few checks. For object storage, this means reading a sample of files.

**Who runs the tests.** The Platform & Infrastructure team runs the restore tests. The team that owns the data — for example, Routing Core for the routing engine database — reviews the results and confirms that the restored data looks correct. The Information Security team reviews the test results as part of the overall security program.

**Test failures.** If a restore test fails, we treat it as an incident. The Platform & Infrastructure team investigates the cause, fixes the backup process, and takes a new backup. The test is then run again to confirm the fix. We do not close a test failure until a restore from a new backup succeeds.

**Documentation.** Each restore test is documented, including which system was tested, when the test ran, and whether it passed. The documentation is stored in Grove so that anyone can review the history of restore tests. If an auditor or a customer asks how we know our backups work, we can show them the test results.

Example: Marek, a field solutions engineer working with clients in Poland, hears from a customer that they are worried about data loss. He wants to reassure them. He checks the restore test documentation in Grove and sees that the customer's data store was successfully restored and verified recently. He shares the summary with the customer, which helps them trust the Kranich Route Cloud.

Example: Ines Duarte, an engineering manager in Berlin, is responsible for a service that writes data to a database. During a routine restore test, the Platform & Infrastructure team finds that the backup is missing a recent batch of records. They investigate and discover that the backup job stopped running after a configuration change. They fix the job, take a new backup, and run the restore test again. The second test passes. Ines is informed of the issue and the fix.

## 5. Questions

If you have questions about this standard, or if you think a system you work with is not covered by an appropriate backup, please reach out. The Information Security team owns this standard and can answer questions about retention, restore tests, and exceptions. You can contact them at security@kranich.example.

If you need help with a backup or restore operation, for example because you accidentally deleted data or you suspect a system is not backed up, contact the Platform & Infrastructure team through the internal help channel. They will guide you through the process.

If you believe a backup has failed, or you notice that a system is not being backed up, report it promptly. You can report it to the Platform & Infrastructure team or directly to the Information Security team. Early reporting helps us fix problems before they become data loss events.

For questions about data handling more broadly, including what data we store and for how long, refer to POL-004. For questions about the cost of backup storage, which is part of our infrastructure budget, contact the Finance team. The Finance team can also help with questions about the financial implications of data retention, such as those covered in FIN-RATES-2026.

Finally, if you are unsure whether this standard applies to a tool or system you are using, ask before you rely on it. A quick question to the Information Security team or the Platform & Infrastructure team is always better than discovering later that your data was not protected. We would rather answer a hundred questions than lose one piece of customer data.

Example: Lea, a people operations specialist in Berlin, wants to store a spreadsheet with employee feedback in a new cloud storage tool that a colleague recommended. She is not sure whether the tool is backed up under this standard. She sends a short message to the Information Security team, who confirm that the tool is not yet covered and recommend she store the file in the approved location instead. Lea follows their advice, and the data stays protected.

This standard is reviewed regularly by the Information Security team. If you have suggestions for improvement, please share them. Backup practices evolve as our systems change, and we want this standard to stay relevant and useful.
