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
- Image-to-PDF downloads kept the original image filename extension. The viewer now
  saves generated copies as .pdf; actual browser downloads cover PNG, JPEG and PDF.
- Source-release allowlist omitted the new build inputs. The reviewed inventory includes them.
- OCR evaluation lint issues and a cleanup-test wrapper missing a new keyword were corrected.

Each functional fix has a regression observed failing before its correction.

CI caught a test harness issue in the new download checks: headless Chromium downloads
an embedded PDF automatically, and the test consumed that event before the click.
The test now first asserts the link's download filename and waits for the corresponding
download. Seven scenarios pass on both CI-style headless shell and system Chromium;
negative controls restoring the old PNG/JPEG names still fail. An unrelated existing
keyless upload test also hit its fixed 100 ms observation window once and passed on
rerun; its product code and test were not changed.
The final server build first failed inside Next.js Google-font URL parsing; the same
unchanged build compiled successfully on retry. No dependencies or font code were changed.

## Verification and release

Final checks and production evidence are recorded in `evidence/ocr-release-2026-09-29/`.
The initial complete backend run was 734 passed / 1 failed; its sole failure was the
old test wrapper described above. The corrected full run passed 742 tests, with 88.22% coverage against the 80% gate.
Real Tesseract end-to-end suite passed 5 tests (including PNG and scanned-PDF uploads).
New extraction browser suite covers schema/field editing across 320/390/1440px,
error/retry handling and actual PNG/JPEG/PDF downloads.
Existing account UI checks: 52/52; design interactions: 6/6; deployment tests: 36/36.
Real Tesseract tests use English data in an isolated local tessdata directory; release
image includes the engine and English language package.

Final production release `/opt/docqa-releases/prod-20260929-digitization-v4` was activated
at 2026-09-29 13:22:22 UTC. Git commit `61c84c8dc8321f1b2e380191b862585ed2b58592`
is pushed to main. [Final GitHub CI](https://github.com/Hortenh1x/docqa/actions/runs/36573965315)
passed all jobs: backend 741 passed / 3 skipped (optional real Tesseract fixtures),
deployment 36 passed, three UI configurations, both Docker builds.
Real OCR was independently exercised locally and in the ARM production image.

Published source archive SHA-256:
`0335c4aceacd98263873fb83132040672501b25dd1e5c88473832471a9fde89f`.
Image verification matched all 182 application/migration/lock files and confirmed
English Tesseract OCR plus searchable PDF output. Activation preserved all 9,778 documents,
295,856 chunks and recorded table counts; PostgreSQL, Redis and other shared-host
containers were not replaced. Synchronous standby and persistent migration image match
were checked by the activation script; monitoring was restored.

Production before activation: `/opt/docqa-releases/prod-20260922-merged-ui`, schema 0014.
Additive schema release targets 0017. Preserve previous images and backup; do not
resume old writers automatically after a schema-changing failure.

Production schema 0017 backup `20260929T130408Z` was restored from encrypted off-host
snapshot `a5c44e7c7b7fde629834b0f86b92fdef475554430349622b436954cb8a5f25ed`.
The database dump, file archive, 9,783 individual files, runtime configuration and source
archive matched their SHA-256 checks. This checks restored artifacts; it is not a new
SQL import/functional database restore test.

Final non-mutating live verification passed on 15 page/viewport combinations
(1440, 390 and 320 px): no page errors or horizontal overflow; readiness 200;
guest schema access 404. The downloaded public source archive matched the release hash.
All 384 published source files also match the final local worktree.

The final release configuration/source was captured in off-host snapshot
`1acb31304018475ad6f7ce213a86c5994e0615a3b83e414ec875b26560c774ba` and restored at
2026-09-29 13:23:59 UTC. All file, dump and configuration comparisons passed again.
It uses the verified schema-0017 data bundle above, taken after the initial feature
activation; the last release only changed the UI filename and browser tests.

## Remaining boundaries

Searchable PDF geometry is approximate after deskew/Tesseract orientation; exact pixel
highlight alignment is not claimed. Recognition quality depends on scan quality and the
installed/configured languages (production default: English). A live paid extraction is
not implied by stub-based integration tests. Original uploads remain separately available.
