# Evaluation results

_Embeddings: text-embedding-3-small@1024 · rerank: none · top-8 after fusion of vector top-30 + FTS top-30 · LLM: deepseek-v4-flash_

Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| access | 32 | 1.00 | 0.498 |
| **all answerable** | 17 | **1.00** | |

## Refusal threshold sweep (gate score = best vector cosine, rerank=none)

| Threshold | Refuses no_answer | Passes answerable | Balanced |
| --- | --- | --- | --- |
| 0.10 | 0.00 | 1.00 | 0.50 |
| 0.12 | 0.00 | 1.00 | 0.50 |
| 0.14 | 0.00 | 1.00 | 0.50 |
| 0.16 | 0.00 | 1.00 | 0.50 |
| 0.18 | 0.00 | 1.00 | 0.50 |
| 0.20 | 0.00 | 1.00 | 0.50 |
| 0.22 | 0.00 | 1.00 | 0.50 |
| 0.24 | 0.00 | 1.00 | 0.50 |
| 0.26 | 0.07 | 1.00 | 0.53 |
| 0.28 | 0.07 | 1.00 | 0.53 |
| 0.30 | 0.07 | 1.00 | 0.53 |
| 0.32 | 0.13 | 1.00 | 0.57 |
| 0.34 | 0.60 | 1.00 | 0.80 |
| 0.36 | 0.67 | 1.00 | 0.83 |
| 0.38 | 0.73 | 1.00 | 0.87 |
| 0.40 | 0.73 | 1.00 | 0.87 |
| 0.42 | 0.80 | 1.00 | 0.90 ← |
| 0.44 | 0.87 | 0.94 | 0.90 |
| 0.46 | 0.87 | 0.94 | 0.90 |
| 0.48 | 0.87 | 0.94 | 0.90 |
| 0.50 | 0.87 | 0.94 | 0.90 |
| 0.52 | 0.87 | 0.94 | 0.90 |
| 0.54 | 0.87 | 0.88 | 0.87 |
| 0.56 | 1.00 | 0.76 | 0.88 |
| 0.58 | 1.00 | 0.71 | 0.85 |
| 0.60 | 1.00 | 0.65 | 0.82 |
| 0.62 | 1.00 | 0.47 | 0.74 |
| 0.64 | 1.00 | 0.29 | 0.65 |
| 0.66 | 1.00 | 0.24 | 0.62 |
| 0.68 | 1.00 | 0.18 | 0.59 |
| 0.70 | 1.00 | 0.06 | 0.53 |

**Recommended `REFUSAL_THRESHOLD`: 0.42** — refuses 80% of off-corpus questions for $0 while passing 100% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 15/15
- False refusals on answerable questions: 1/17
- Citation precision (cited docs ∩ expected docs): 17/17

## Access control

- Restricted questions (asked under a role that may not see the answer): 15
- Retrieval leaks (a chunk outside the role's labels surfaced): 0/15
- Reveal hint names the unlocking label: 15/15
- End-to-end leaks (an answer instead of a refusal): 0/15
- Unlock questions (asked under the right role), recall@8: 17/17
