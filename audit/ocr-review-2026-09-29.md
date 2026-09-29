# Digitization review and release — 2026-09-29

User authorized fetching Claude's work, reviewing it, fixing confirmed defects, and deploying.

## Starting state

`origin/claude/digitization-modules-f2ubud` and local main both pointed to `1585be0`.
The clean local checkout already contained all five commits ahead of origin/main.
No missing feature code needed merging. Review branch: `codex/ocr-review-release`.

Claude implemented OCR for scanned PDFs and image uploads (including multipage TIFF),
preprocessing and Tesseract/optional vision providers, derived searchable PDFs, and
schema-driven structured field extraction with source evidence, edits and CSV/JSON export.
UI additions are Library → Fields and /schemas. Migrations 0015–0017 include the earlier
Notion source connector; it remains disabled without configured source credentials.

## Confirmed issues corrected

- Searchable PDFs lost Unicode, clipped long lines, omitted text without bounding boxes,
  and ignored phone EXIF orientation. Regression fixtures now preserve these cases.
- Large PDF rasters and preprocessing arrays were not bounded; oversized image decode
  exceptions escaped parser error handling. Raster/image work is bounded before filters.
- NULL section paths dropped all unheaded text from extraction and access-label collection.
- Guest tenant resolution exposed owner extraction resources. Guest reads are rejected.
- Queue publication failures and worker loss left jobs pending/processing indefinitely.
  Recovery republishes pending jobs and marks expired claims failed for explicit retry.
- Edits retained stale indexed facts; failed reindexing orphaned the prior facts passage.
  Edits invalidate facts, and final results/facts replace together under consistent locks.
- Structured-output fallback/repair made multiple paid calls against one reservation.
  Each HTTP attempt now receives independent admission and settlement.
- OCR ran before persisted billing attribution; eager thread bridging lost context.
  Attribution now surrounds parsing and survives the thread bridge.
- Hosted vision image-token cost cannot currently be bounded accurately; budget-controlled
  user vision calls fail closed. Production uses local Tesseract. Operator/local use remains.
- Backup verification omitted image MIME types, derived PDFs, and new table counts.
  Backup hydrates/verifies derived files and restores old manifests compatibly.
- Source-release allowlist omitted the new build inputs. The reviewed inventory includes them.
- OCR evaluation lint issues and a cleanup-test wrapper missing a new keyword were corrected.

Each functional fix has a regression observed failing before its correction.

## Verification and release

Final checks and production evidence are recorded in `evidence/ocr-release-2026-09-29/`.
The initial complete backend run was 734 passed / 1 failed; its sole failure was the
old test wrapper described above. The corrected full run passed742 tests, with88.22% coverage against the80% gate.
Real Tesseract end-to-end suite passed5 tests (including PNG and scanned-PDF uploads).
New extraction browser suite passed4 scenarios across320/390/1440px.
Existing account UI checks: 52/52; design interactions: 6/6; deployment tests: 36/36.
Real Tesseract tests use English data in an isolated local tessdata directory; release
image includes the engine and English language package.

Production before activation: `/opt/docqa-releases/prod-20260922-merged-ui`, schema0014.
Additive schema release targets0017. Preserve previous images and backup; do not
resume old writers automatically after a schema-changing failure.

## Remaining boundaries

Searchable PDF geometry is approximate after deskew/Tesseract orientation; exact pixel
highlight alignment is not claimed. Recognition quality depends on scan quality and the
installed/configured languages (production default: English). A live paid extraction is
not implied by stub-based integration tests. Original uploads remain separately available.
