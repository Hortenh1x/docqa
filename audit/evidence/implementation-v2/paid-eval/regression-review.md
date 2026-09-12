# AI regression after v2 changes — 2026-09-10

The original [99-execution report](review.md) is historical. Its judge retrieved
context again; it did not save the exact original chunk IDs. Do not interpret the
original report's “actual trimmed context” wording as proof of identical inputs.
The updated harness captures the actual generation blocks and judges those directly.
HTTP evaluation without that capture explicitly skips the judge.

## Diagnosis and changes

- `p0609` has an invalid original expectation: both amounts are in Finance-only
  POL-018 §3. The generator now inherits document/section visibility before choosing
  open/partial facts. Canonical historic golden YAML and numeric facts were preserved;
  the regression carries an explicit corrected expectation. In the initial sample,
  reclassifying this case gives 24/24 expected refusals and one false refusal among
  73 answerable questions (rather than 23/23 and two among74). Raw evidence is unchanged.
- Fresh [candidate capture](regression-diagnosis/candidates.json) locates the relevant
  historical rule (`h0090`, chunk1046) at rank30 and latest deploy window (`m0520`,
  chunk1527) at rank33. Neither reached the old top20 answer context. This proves a
  retrieval-window limitation in this snapshot; it does not prove the old historical
  prompt alone caused the wrong answer.
- The new default accepts 40 chunks within18,000 tokens, replacing20/9,000. Prompts
  preserve the requested date/version/scope, answer supported independent parts and
  never infer withheld values. They treat embedded source instructions as data.
- The standup fact (`m0516`, chunk1525) was already rank16. The corrected prompt and
  expanded context together produced the correct answer; their individual effect
  was not isolated. Broad FTS changes and alternative context allocation were rejected
  because offline diagnosis did not support them.

## Targeted real-provider result

[10 cases and original contexts](regression-answers/results.json), selected to cover
the observed failures, a genuine partial answer and two deny/unlock role pairs:

- 7/7 answerable questions answered correctly; no false refusals in these seven.
- 8/8 generated answers judged faithful using their original trimmed context.
- 2/3 expected-denial cases returned the hard refusal sentinel. `p0609` instead
  explained that the numeric thresholds were unavailable, then gave grounded
  nonnumeric approval guidance. It disclosed neither protected amount. This is
  **not** a claim of 3/3 hard-refusal compliance.
- No forbidden access label reached context; no specified hidden value appeared.
- `h0090`:16 weeks; `m0516`:14 minutes; `m0520`:7 hours; `x0533`:10 business days and
  a correct clarification of the question's mistaken cross-reference.

The model/judge are remote DeepSeek Flash / GPT-4.1-mini, embeddings OpenAI small@1024.
This is a small diagnostic regression, not a repeat of the full corpus, a statistical
quality guarantee, an account-isolation test or a production load test. Larger context
uses more of each user's unchanged daily allowance. The original .env was not edited;
existing deployments with explicit20/9,000 overrides must apply the new release values.

## Shared test budget and source safety

The [last spend ledger](regression-answers/spend.json) **includes all prior calls**:
observed peak/cache-miss upper estimate **$0.47832642**, unknown-usage reserve **$0**,
cumulative conservative nonrefundable reservations **$2.73150544** against the original
**$3** gate. Do not add previous ledgers to it. Provider usage is an upper estimate,
not an invoice; cached input can cost less.

All work used read-only copies of three specifically named synthetic collections
into disposable PostgreSQL. Snapshot counts/hash are in each metadata file; exact
contexts contain only that synthetic material. No user originals were submitted and
no production database or corpus facts were changed. The independent AI review and
20 focused offline tests passed. See [runner](../../../regression_eval.py).
