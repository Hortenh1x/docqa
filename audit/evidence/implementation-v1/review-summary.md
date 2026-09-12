# Review record — approved implementation v1, 2026-09-10

Reviews were read-only and separate from each reviewed implementation. Findings were
confirmed before changes; no commits or production actions were performed.

- Backend lifecycle/recovery review found a collection-version gap on delete/reprocess,
  insufficiently early stream cleanup, replay policy narrowing and default pipeline
  version capture. These were corrected and covered by deterministic integration tests.
  Final reviewer result: no remaining blocking findings; focused generation/provider
  suite 21 passed and reviewed integration suite 26 passed. Final root suite supersedes
  these intermediate counts (252 passed).
- UI spec and quality review found the expired answer remained in the idle aria-live
  text. The root corrected AskScreen and added a body-text assertion; three expiry
  scenarios independently passed against the final production UI container.
  Reviewer result: spec PASS, quality PASS for approved W08 plus cleanup behavior.
- Infrastructure W06/W11 reviewer inspected configuration/identities, SQL grants,
  fresh/existing-volume paths, consistent backup, isolated restore, cleanup errors,
  monitoring and both CI UI modes. Independent deploy tests 6 passed; shell syntax and
  diff checks passed. Reviewer result: spec PASS, quality PASS for the local scope.
- Final root checks additionally preserve TOP_K_FTS=0 for existing vector-only evals,
  accept EMBEDDING_DIM from environment strings, verify negative input/file/header
  boundaries and fence in-flight suggested questions across both delete and wipe.

Scope limitations are retained in application-assessment.md: real provider quality/cost,
production version/ingress, existing grants, real backup/rollback/cutover, alert delivery,
retention/operator/license choices and wider browser/assistive coverage are not established
by these reviews.

- Additional W10 accessibility review reproduced and corrected long-answer/resize overflow
  and low-contrast placeholder/pending states. The bounded suite measures 42 layout/semantic
  cases, 16 rendered contrast pairs and 3 keyboard routes, with explicit methodology and
  no full WCAG/native zoom/screen-reader claim. Final Docker verification is recorded in
  ui-accessibility-results.json; the keyless CI job runs the same suite.

Final W10 read-only spec/quality review: PASS, no blocking regression. On the rebuilt
keyless Docker image the slash-key test initially ran before the passive effect was
attached; instrumentation reproduced2/12 such early actions. The test now waits for
a controlled input interaction to enable Ask before testing one slash action. No UI
source workaround or sleep/retry was added. The readiness sequence passed20/20 and
the full42/16/3 suite passed on Docker. See ui-accessibility-focus-diagnosis.json and
ui-accessibility-results.json. Root visually checked the final320px long answer and
640px doubled-text screenshots.
