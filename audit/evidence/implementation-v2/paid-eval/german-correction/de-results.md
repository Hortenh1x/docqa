# Evaluation results

_Isolated synthetic snapshot; deepseek-v4-flash (provider aliases to V4.1); OpenAI embeddings@1024; gate=0.28; top_n=20; actual trimmed context; judge=gpt-4.1-mini_

Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`

## Retrieval quality by category

| Category | Questions | Recall@20 | Mean gate score |
| --- | --- | --- | --- |
| access | 2 | 1.00 | 0.517 |
| **all answerable** | 1 | **1.00** | |

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
| 0.26 | 0.00 | 1.00 | 0.50 |
| 0.28 | 0.00 | 1.00 | 0.50 |
| 0.30 | 0.00 | 1.00 | 0.50 |
| 0.32 | 0.00 | 1.00 | 0.50 |
| 0.34 | 0.00 | 1.00 | 0.50 |
| 0.36 | 0.00 | 1.00 | 0.50 |
| 0.38 | 1.00 | 1.00 | 1.00 |
| 0.40 | 1.00 | 1.00 | 1.00 |
| 0.42 | 1.00 | 1.00 | 1.00 |
| 0.44 | 1.00 | 1.00 | 1.00 |
| 0.46 | 1.00 | 1.00 | 1.00 |
| 0.48 | 1.00 | 1.00 | 1.00 |
| 0.50 | 1.00 | 1.00 | 1.00 |
| 0.52 | 1.00 | 1.00 | 1.00 |
| 0.54 | 1.00 | 1.00 | 1.00 |
| 0.56 | 1.00 | 1.00 | 1.00 |
| 0.58 | 1.00 | 1.00 | 1.00 |
| 0.60 | 1.00 | 1.00 | 1.00 |
| 0.62 | 1.00 | 1.00 | 1.00 |
| 0.64 | 1.00 | 1.00 | 1.00 |
| 0.66 | 1.00 | 1.00 | 1.00 ← |
| 0.68 | 1.00 | 0.00 | 0.50 |
| 0.70 | 1.00 | 0.00 | 0.50 |

**Recommended `REFUSAL_THRESHOLD`: 0.66** — refuses 100% of off-corpus questions for $0 while passing 100% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 1/1
- False refusals on answerable questions: 0/1
- Citation precision (cited docs ∩ expected docs): 1/1

## LLM-judged answer quality (judge: gpt-4.1-mini)

- Faithfulness (every claim supported by the excerpts): 1/1
- Correctness vs the golden expected answer: 1/1

## Access control

- Restricted questions (asked under a role that may not see all of the answer): 1
- Retrieval leaks (a chunk outside the role's labels surfaced): 0/1
- Reveal hint names the unlocking label: 1/1
- Restricted values appearing in an answer (the real leak test): 0/1
- Answered from open content instead of refusing: 0/1
- Unlock questions (asked under the right role), recall@20: 1/1
