# Grounded indirect comparison diagnostic

Date: 2026-09-20

This is a bounded diagnostic for the standalone question:

> and what year was financially better for amazon? 2017 or 2022?

It is not a score for FinanceBench, the production collection, or comparative questions in
general. Conversation history is intentionally outside scope.

## Reproduce

The retrieval-only run downloads three fixed public FinanceBench PDFs, verifies SHA-256 and PDF
page counts, parses/chunks them with the current application code, embeds them, and stores PDFs and
vectors outside Git:

```bash
uv run python -m eval.run_indirect_comparison
```

Every run verifies the PDF hashes/page counts and reparses the documents with the current parser and
chunker. `/tmp/docqa-indirect-comparison/vectors.json.gz` is reused only when its schema, embedding
model, current chunk metadata/content, and complete query-input fingerprint match. Any mismatch
rebuilds the vectors. To force a rebuild:

```bash
uv run python -m eval.run_indirect_comparison --refresh-embeddings
```

`--no-download` disables document downloads but does not bypass hash, parse, statement, or cache
validation. If current inputs differ from the cache, rebuilding still requires the configured
embedding provider.

The optional live answer run uses the real `app.generation.service.run_query` orchestration but
patches retrieval to the isolated cached fixture and patches query recording to a no-op. It does not
open or write the application database:

```bash
uv run python -m eval.run_indirect_comparison --with-answers --repeats 2
```

The first embedding pass measured 200,637 tokens and approximately $0.004013 with
`text-embedding-3-small@1024`. Live answer runs use the configured LLM and incur provider cost.

## Fixed source artifacts

The manifest is `eval/indirect_comparison.yaml`. Sources are the files with these exact official
FinanceBench filenames:

| File | SHA-256 | PDF pages | Role |
| --- | --- | ---: | --- |
| `AMAZON_2017_10K.pdf` | `f8af08ff6c4147351ec3a6e5e2c74e104678ce68fb0d6d476b1e43f685c09a3f` | 85 | evidence |
| `AMAZON_2022_10K.pdf` | `084ef3d6031c4b57169b32ae6a878a86ebbcbc7bb868030e3170d04392b4096e` | 81 | evidence |
| `BESTBUY_2020_10K.pdf` | `b699823b02e3545752f28cc579694dc9c81ef3b7a21b751c96f8b3a175804ec8` | 71 | distractor |

The current parser extracts both complete statements. Page numbers below are the physical/document
page numbers in the PDFs; the chunks include the following page because section boundaries cross a
page break.

| Filing | Current chunk | Statement page | Net sales | Operating income | Net income (loss) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Amazon 2017 | 89, pages 38–39 | 38 | $177,866m | $4,106m | $3,033m |
| Amazon 2022 | 88, pages 37–38 | 37 | $513,983m | $12,248m | $(2,722)m |

Parser loss is therefore not the cause in this fixture.

## Screenshot incident boundary

The local database did not contain Amazon or Best Buy documents or either screenshot question, so
the screenshot's actual follow-up retrieval and refusal stage remain unverified. The 36 passages
shown for the preceding question cannot establish the follow-up's context.

The query row can distinguish stages if the real collection becomes available. A retrieval-gate
refusal records no model or tokens and no query citations (`app/generation/service.py:308-342`). A
model refusal has model/usage and records its context citations. An empty visible completion is a
separate generation failure; it must not be diagnosed as missing documents.

## Retrieval coverage

This sweep uses OpenAI vector similarity only, the three documents above, frozen side-specific
queries, and the implemented `round_robin_chunks` helper. It does not exercise PostgreSQL FTS, RRF,
a reranker, or access-restricted content.

| Context cap | Original single query | Original + two side queries |
| ---: | --- | --- |
| 8 | neither complete statement | 2017 at position 8; 2022 absent |
| 12 | neither complete statement | 2017 at position 8; 2022 absent |
| 16 | 2022 at position 15; 2017 absent at rank 17 | 2017 at 8; 2022 at 14 |
| 20 | 2017 at 17; 2022 at 15 | 2017 at 8; 2022 at 14 |
| 40 | 2017 at 17; 2022 at 15 | 2017 at 8; 2022 at 14 |

Cap 16 is the natural stressed case where planning adds complete two-sided evidence. Cap 8 is too
narrow for the round-robin merge to retain both complete statements. Cap 20/40 shows that the
ordinary query already covers both when the window is wide enough.

The current configured top-40 pipeline was also called with the same three-file fixture and current
answer prompt. It answered from both statements: 2017 was better on net income, while 2022 was
larger on sales and operating income. That call used 16,465 prompt and 3,114 completion tokens and
cost approximately $0.008676. This is a production-style configuration check, not a call against
the deployed production corpus.

## Planner-only smoke checks beyond the target comparison

The configured `deepseek-v4-flash` model at the normal 4,096-token limit also received two fixed
questions with no documents, retrieval results, or hidden metadata. Both outputs were strict JSON.

| Original question | Parsed `queries` | Prompt/completion tokens | Latency | Cost |
| --- | --- | ---: | ---: | ---: |
| `What was Amazon's net sales in 2022?` | `[]` | 318 / 25 | 911 ms | $0.000125 |
| `Compare the 2026 travel allowance for employees in Germany and the UK.` | `2026 employee travel allowance in Germany`<br>`2026 employee travel allowance in the UK` | 322 / 308 | 2,083 ms | $0.000466 |

This is a planner-prompt probe only. It shows that a simple direct lookup avoids expansion and that
a non-financial comparison can produce two bounded facets. It does not evaluate retrieval or answer
quality for Germany or the UK. The raw local evidence is
`/tmp/docqa-indirect-diagnostic/planner_probe_results.json`; the current helper call to reproduce
the planner behavior is `await plan_queries(get_llm_provider(settings), question)` from
`app.retrieval.planning`.

## Pre-retry live A/B at cap 16

The source diff hash was stable before and after these calls. All five runs preserved the original
gate score, ran original retrieval first, disabled hidden-label probes for expansions, reused the
same access labels, capped expansions at three, deduplicated context, and matched aggregated
planner/answer usage in `DoneEvent` and the would-be database record.

| Mode | Outcome | Complete statements in context | Cost | Latency |
| --- | --- | --- | ---: | ---: |
| planning off, run 1 | answered; both filings cited | 2022 only (#15) | $0.006214 | 14.3 s |
| planning on, run 1 | answered; both filings cited | 2017 #5; 2022 #14 | $0.005344 | 14.1 s |
| planning off, run 2 | answered; both filings cited | 2022 only (#15) | $0.006621 | 14.7 s |
| planning on, run 2 | answered; both filings cited | 2017 #2; 2022 #9 | $0.006459 | 17.5 s |

All answers named a criterion and avoided an unqualified universal winner. The first planned answer
used net income only after saying the term was undefined. The second planned answer compared
profitability, sales, and operating income. The baseline also answered twice from partial 2017
chunks, so this fixture proves better full-statement coverage, not a higher answer rate.

The missing-evidence control asked for 2022 versus 2025 net income in EUR. Its planner consumed the
full 4,096 completion allowance and emitted no visible JSON, so planning correctly failed open to
the original retrieval. The answer cited only Amazon 2022, reported the $(2,722)m USD loss, and said
2025/EUR/exchange-rate evidence was absent. It did not invent a conversion or cite Best Buy. The
planner's failed attempt added 17.1 seconds and $0.005013, which is the measured worst case in this
bounded run.

These five pipeline runs made eight LLM calls and cost $0.032058, plus approximately $0.000002 for
new query embeddings.

## Pre-retry cap-8 follow-up

One non-adaptive planning-off/on pair was run and then stopped. Both calls produced empty visible
completions after using the full 4,096 answer completion tokens, and the old pipeline converted both
to `empty_completion` refusals. Planning added the 2017 complete statement at context position 4,
but the 2022 complete statement did not fit in the eight-block merge.

| Mode | Outcome | Prompt/completion tokens | Cost | Latency |
| --- | --- | --- | ---: | ---: |
| off | empty completion/refusal | 3,218 / 4,096 | $0.005881 | 17.1 s |
| on | planner succeeded; answer empty/refusal | 3,663 / 4,328 aggregated | $0.006292 | 20.2 s |

This pair does not demonstrate false-refusal recovery. It exposes completion nondeterminism and an
evidence-window limit. No additional question was searched to manufacture a win.

## Final same-settings retry build: one cap-8 planned run

After the empty-completion retry was implemented and its focused tests were green, exactly one
planning-enabled cap-eight call was made. The app-source diff hash was identical before and after:
`7d9d0a05375effe23f93263a310569564927ff7a736b2a948368cf269d3d03ab`.

The first answer attempt completed visibly, so this particular live run did not invoke the retry. It
answered with an explicit consolidated-operating-income criterion: 2022 had $12,248m versus $4,106m
in 2017. It also gave supported 2017 net sales ($177,866m), 2017 net income ($3,033m), and the 2022
segment operating-income values, then stated that a full bottom-line comparison was unavailable
because 2022 net sales and net income did not fit this context. Every numeric claim appears in the
cited Amazon 2017 or Amazon 2022 context block. The answer cites both filings and does not assert an
unqualified universal winner.

The planner used 322 prompt/268 completion tokens and cost $0.000418. The answer used 3,593/694 and
cost $0.001911. Aggregated pipeline usage was 3,915/962, $0.002329, with 6.7-second end-to-end
latency; the two new query embeddings cost approximately $0.000001. Gate, access-label, expansion,
deduplication, usage, cost, and would-be recording checks all passed.

The live call proves that the final code can return a grounded qualified answer on this narrow
context. It does not itself exercise the retry because the provider succeeded on its first answer
attempt. The deterministic focused tests cover both retry branches:

- `tests/unit/test_generation.py::test_empty_answer_retries_once_with_same_evidence_and_succeeds`
  verifies identical evidence and successful second output;
- `tests/unit/test_generation.py::test_two_empty_answers_emit_provider_error_and_record_all_usage`
  verifies that two empty attempts end in `provider_unavailable`, record all usage, and do not record
  a document refusal;
- `tests/unit/test_generation.py::test_no_answer_sentinel_does_not_retry` verifies that an honest
  `NO_ANSWER` remains final;
- `tests/integration/test_billing.py::test_empty_answer_retry_uses_a_third_provider_reservation`
  verifies planner plus both answer calls are reserved and settled.

## Thinking-mode control: negative experiment

[DeepSeek's official thinking-mode documentation](https://api-docs.deepseek.com/guides/thinking_mode/)
documents `{"thinking":{"type":"disabled"}}` for its OpenAI Chat Completions interface. The
same frozen planning-off top-eight context was probed without changing facts or the answer prompt.

- A repeat with thinking enabled completed normally this time: 537 reasoning tokens, a visible
  supported partial answer, 3.9 seconds, and $0.001868. This confirms nondeterminism; it does not
  recover finish metadata from the earlier empty call because the current provider adapter discards
  finish reason and reasoning fields.
- Thinking disabled returned visible text in 1.4 seconds for $0.001175, but it answered an English
  question in Chinese and opened with the unsupported claim that 2017 was financially better before
  acknowledging that 2022 profitability was unavailable. It failed grounding/language behavior.
- On the missing-2025/EUR control, thinking disabled did return a concise grounded partial answer in
  1.1 seconds for $0.001108.

The no-thinking answer retry was rejected. The implemented retry uses the same provider, model,
settings, prompt, and context. It occurs only after an empty visible answer, never after
`NO_ANSWER`; it does not retrieve again or change sources; all attempts are counted. If a second
attempt is also empty, the pipeline emits `provider_unavailable` instead of falsely reporting that
documents lack the answer.

## What the evidence supports

Confirmed:

1. The necessary Amazon values, years, units, and page locations survive the current parser.
2. The unchanged answer prompt can produce a grounded qualified comparison when evidence is
   sufficient.
3. Side-specific retrieval materially raises the complete statement chunks and balances the two
   periods at cap 16.
4. Existing `eval/results_financebench.md` independently attributes 15 of 25 sampled refusals to
   the right filing being present while the answering chunk was absent; prompt-only arithmetic
   relaxation previously worsened aggregate behavior.
5. DeepSeek consumed the full configured completion allowance without emitting a visible answer.
   That observation is consistent with reasoning exhaustion, but the failed response's finish reason
   and reasoning fields were not captured by the provider adapter. These failures must remain
   distinct from honest document refusals.

The screenshot has several unranked plausible explanations: broad retrieval omitted one or both
answering blocks; the original-query score failed the retrieval gate; or generation exhausted its
completion budget without visible output. The exact incident record is unavailable, and the baseline
fixture answered from partial evidence, so the local evidence does not establish which explanation
applies.

This report makes no whole-FinanceBench improvement claim. The full collection has far more
competition, hybrid ranking may differ, and this fixture has no restricted chunks. Access, billing,
normal-direct-query, fallback, and focused unit regressions were completed separately for the
implementation; their results do not expand this fixture's retrieval claim. On 2026-09-21, fresh
ruff, format, and mypy checks passed; the coverage-gated suite passed 527 tests at 87.79% (including
the four evaluation-cache regressions), deploy tests passed 16 tests, and the accounts UI build,
typecheck, and browser regressions passed (33 accounts and 6 design tests).
