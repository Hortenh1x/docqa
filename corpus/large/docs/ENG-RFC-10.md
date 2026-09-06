---
doc_id: ENG-RFC-10
title: RFC-10: Search over fleet documents
version: "1.0"
effective_date: 2025-10-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-10: Search over fleet documents

## 1. Context

The Kranich Route Cloud stores a growing number of fleet-related documents: uploads from customer success managers, field solutions engineers, and clients themselves. These include delivery notes, vehicle inspection reports, driver instructions, and correspondence attached to routes or vehicles.

Today, finding a document means knowing where it was uploaded. Documents live inside a route, a vehicle profile, or a customer workspace. There is no single place to search across all of them. When a customer asks "do we have the inspection report for the truck that served the Gdansk route last spring?" the answer depends on someone remembering which workspace held the file.

This RFC proposes a lightweight, full-text search layer over fleet documents. It is scoped to metadata and extracted text, not to binary content analysis. The goal is to let employees and authorized customers find documents by content, sender, vehicle, or route reference, without changing where documents are stored.

## 2. Proposal

We introduce a search index service, internally called Fleet Search, that ingests document metadata and extracted text from existing storage. The service exposes a single query endpoint used by the web application's global search box.

The index is built from events already emitted when documents are uploaded or updated. We do not read the primary storage directly on every query. Instead, a background worker consumes document lifecycle events, extracts text where feasible, and writes to an index optimized for full-text queries.

Search results point back to the original document location. Fleet Search never becomes the source of truth; it is a derived, replaceable index. If the index is rebuilt, it is rebuilt from the document store, not from itself.

## 3. Details

### Scope of indexed documents

We index documents attached to routes, vehicles, and customer workspaces. This includes PDFs, plain text files, and common office formats. Images with embedded text are out of scope for the initial version; we note them in open questions.

Documents are indexed with the following fields:

- filename and file type
- extracted text, where available
- uploader name and email
- customer workspace identifier
- associated route or vehicle identifier, where present
- upload timestamp

Access control is applied at query time. The search service receives the requesting user's permissions and filters results accordingly. A customer success manager in Berlin sees documents for their assigned customers; a field solutions engineer in Poland sees documents for their local customer sites. No document content leaves the existing authorization boundary.

### Text extraction

A worker pulls each new document, runs extraction based on file type, and stores the resulting text alongside the metadata in the index. Extraction failures are logged and do not block the upload flow. Documents that cannot be extracted remain searchable by metadata only.

We reuse the extraction library already present in the platform for invoice processing; see the document catalog entry for that component in Grove. We do not build a new extractor.

### Index lifecycle

Documents are added to the index shortly after upload. Updates to metadata trigger a re-index of that document. Deletions remove the document from the index. A reconciliation job runs periodically to compare the index against the document store and correct drift.

The index is rebuilt from scratch during major platform migrations. Rebuild is an offline operation; the search box shows a notice while it runs.

### Query behavior

Queries match against filename, extracted text, uploader, and associated identifiers. Results are ranked by relevance, with exact filename matches ranked above partial content matches. The user interface groups results by customer workspace so that a search for "inspection" returns a list of files grouped by the customer they belong to.

The search box is the same one used for navigation today. Typing a query shows document results below the existing navigation results. Clicking a document result opens the document in its original context.

## 4. Alternatives considered

### Build search into the primary document store

We considered adding full-text search directly to the existing document storage layer. This would avoid a separate service and reduce moving parts. We rejected it because the storage layer is optimized for write throughput and retrieval by known identifier, not for ad-hoc text queries. Adding search there would couple indexing performance to the primary write path and make schema changes riskier.

### Use a third-party hosted search product

A hosted search product would reduce operational burden and give us advanced features quickly. We rejected it for two reasons. First, fleet documents often contain customer-specific routing data; sending that text to an external service requires additional data-processing agreements and complicates our compliance story. Second, the Platform & Infrastructure team wants to keep the search index inside our existing network boundary, consistent with how we handle other derived data stores.

### Search only metadata, not content

A minimal version would index filenames, uploaders, and associated route or vehicle identifiers, skipping text extraction entirely. This is simpler and cheaper. We rejected it because the most common search scenario is content-based: a customer success manager remembers a phrase from a delivery note, not the filename. Metadata-only search would fail the primary use case.

## 5. Rollout

We roll out in stages, starting internally.

First, we enable Fleet Search for employees only. Customer success managers and field solutions engineers get access to the search box and see document results. We collect feedback on result quality and query behavior for a few weeks.

Second, we enable search for a small set of pilot customers. These customers already use the document upload feature heavily. We work with their success managers to confirm that access control behaves correctly and that results are useful.

Third, we enable search for all customers who have the document feature enabled. This happens after the pilot shows no access-control issues and after we have updated the user documentation in Grove.

Throughout rollout, the Platform & Infrastructure team monitors index lag and query latency. The Customer Success team owns communication with pilot customers. The Go-to-Market team prepares release notes for the general availability announcement.

Rollback is straightforward: we disable the search endpoint in the web application. The document store is unaffected, and existing upload and retrieval flows continue to work as before. The index can remain in place for a later re-enable, or it can be deleted; it is derived data and carries no state that cannot be rebuilt.

## 6. Open questions

- Should image-based documents, such as scanned inspection sheets, be included in a later iteration? If so, we need an OCR pipeline and a decision on where it runs.
- Do we index documents attached to chat threads inside customer workspaces, or only documents attached to routes, vehicles, and workspaces? Chat attachments are not currently in scope.
- How do we handle documents that contain text in multiple languages, given that our customers operate across Poland, Germany, and other markets? The extraction library handles UTF-8, but ranking quality across languages is untested.
- Should the index retain deleted documents for audit purposes, or should deletion remove them immediately? Current plan is immediate removal, but the Customer Success team has asked whether audit requirements suggest otherwise.
- Who owns the reconciliation job's alerting? Platform & Infrastructure builds it, but the on-call rotation for search-related alerts is not yet assigned.

We welcome comments from Routing Core, Fleet Insights, and Customer Success on the open questions above. Please reply on the RFC thread in Grove by the end of the comment period noted there.
