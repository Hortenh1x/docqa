---
doc_id: ENG-RFC-04
title: RFC-04: Bulk import service
version: "1.0"
effective_date: 2025-04-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-04: Bulk import service

## 1. Context

Platform & Infrastructure owns the data ingestion path for Kranich Route Cloud. Customers of mid-size logistics operators regularly need to bring their historical route, vehicle, and order data into the system when they onboard or when they migrate from a legacy tool. Today, the only supported path is the interactive upload in the web application, which works well for small files but becomes painful for large exports that customers often have.

The Routing Core team has told us that their customers frequently prepare files in a spreadsheet format or as CSV exports from their existing transport management system. These files can be sizable and contain many thousands of rows. Uploading them through the browser often times out, and the user has no way to resume or to monitor progress. This leads to frustration and support tickets.

We also hear from Customer Success that the manual import process ties up their time. Deniz, a customer success manager in Berlin, recently spent several sessions with one customer walking them through splitting a large export into smaller chunks. That is not a scalable way to serve our customers.

This RFC proposes a dedicated bulk import service that accepts large files asynchronously, validates them against the same rules as the interactive upload, and reports per-row issues in a structured way. The service will be owned by Platform & Infrastructure and will be the recommended path for any import above a modest size.

## 2. Proposal

We will build a bulk import service as a separate component within the Kranich Route Cloud platform. The service will expose a presigned upload endpoint so that customers can push a file directly to object storage without streaming it through the application servers. Once the upload completes, the service will enqueue a processing job.

The processing pipeline will read the file in a streaming fashion, validate the schema and the data types, and then apply the same business rules that the interactive import uses today. Any row that fails validation will be collected with a human-readable reason. At the end of the run, the service will produce a summary and a downloadable error report.

The user experience will be a new section in the web application called "Bulk imports." From there, a user can start an import, see its status, and download the results. Status transitions will be: pending, validating, completed with warnings, and failed. A failed import will not partially apply any rows; the service will treat the file as a single transaction.

For the initial version, the service will support the same file formats as the interactive import. We will keep the interactive path untouched for small files.

## 3. Details

The service will consist of three components: an API layer that issues presigned URLs and tracks import jobs, a worker that performs the validation and ingestion, and a storage bucket for the raw files and the result reports.

Bulk imports are capped at 4 GB per file. Files larger than that will be rejected at the presign step with a clear error message. There is no limit on the number of files a customer may submit, but we will apply a simple concurrency limit per customer to protect the platform — see open questions.

The worker will read the file in chunks and validate each row against a shared validation library. This library currently lives inside the monolith and is used by the interactive import. We will extract it into a shared package so that both paths stay consistent. If the library evolves later, both import paths will benefit.

The error report will be a CSV file with one row per invalid record, containing the original line number, the offending field, and the reason. The summary will show counts of valid and invalid rows in words only, so that users can quickly judge whether they can proceed.

Authentication and authorization will reuse the existing platform session and role model. Only users with the "import data" permission will be able to start a bulk import. The presigned URL will be scoped to a single object and will expire promptly.

We will add structured logging and metrics for the pipeline. The service will emit an event when an import finishes, which Customer Success can subscribe to. This way, Deniz and her team can proactively reach out to customers whose import failed instead of waiting for a support ticket.

The raw uploaded files will be retained for a limited period and then deleted automatically. The result reports will be kept longer, because customers may need them for auditing. Access to the storage bucket will be restricted to the service account and to the security team.

## 4. Alternatives considered

We considered extending the existing interactive upload to handle larger files. This would have been the least invasive option, but the browser-based flow is not well suited for long-running transfers. Connection drops would still lose progress, and the application servers would need to buffer the whole file in memory.

We also discussed a fully synchronous import where the user pastes the data into a text area. That approach does not scale to the file sizes our customers actually have, and it would make the error reporting unwieldy.

Another option was to build the bulk import directly into the Routing Core service, since that team owns the domain logic. However, the import path is a cross-cutting concern that affects Fleet Insights and other future consumers as well. Owning it in Platform & Infrastructure keeps a single ingestion story and avoids duplicating validation logic in several places.

We briefly considered using a third-party ETL tool. That would have reduced our build effort, but it would introduce a new vendor dependency and make it harder to keep the validation rules aligned with the product. The shared validation library gives us that alignment without the extra cost.

## 5. Rollout

We will build the service behind a feature flag and first roll it out internally. The Routing Core and Customer Success teams will use it with sample data to verify the behavior. After that, we will enable it for a small set of pilot customers who have expressed interest in larger imports. Marek, a field solutions engineer who works with clients in Poland, has already identified two customers that would benefit from testing the service in a real migration scenario.

Once the pilot phase concludes without critical issues, we will make the feature generally available to all customers. The interactive upload will remain as the default for small files, and the web application will suggest the bulk import path when a file exceeds a reasonable size.

Documentation for the new section will be added to the help center before the general availability. The Customer Success team will receive a short briefing so they can answer questions confidently.

## 6. Open questions

- Should we allow resumable uploads for very large files, or is a presigned URL with a single PUT sufficient for the initial version?
- How long should raw files be retained before deletion? We have a draft answer, but we want input from the security team.
- Do we need to support a dry-run mode where customers can validate a file without applying any data? This would be useful for migrations, but it adds complexity to the transaction handling.
- Should the error report be limited to the first set of invalid rows, or is it acceptable to produce a full report for a 4 GB file?
- What concurrency limit per customer is appropriate? We will start conservatively and adjust based on observed load.
- Who should own the shared validation library in the long term? Platform & Infrastructure can maintain it, but Routing Core may want a say in its evolution.
