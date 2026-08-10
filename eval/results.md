# Evaluation results

_Embeddings: bge-m3 · rerank: none · top-8 after fusion of vector top-30 + FTS top-30 · LLM: qwen2.5:7b-instruct_

Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| direct | 10 | 1.00 | 0.608 |
| table | 4 | 1.00 | 0.620 |
| multi_doc | 3 | 1.00 | 0.631 |
| version | 3 | 1.00 | 0.642 |
| buried | 2 | 1.00 | 0.633 |
| german | 3 | 1.00 | 0.571 |
| no_answer | 5 | — | 0.488 |
| **all answerable** | 25 | **1.00** | |

## Refusal threshold sweep (gate score = best vector cosine, rerank=none)

| Threshold | Refuses no_answer | Passes answerable | Balanced |
| --- | --- | --- | --- |
| 0.30 | 0.00 | 1.00 | 0.50 |
| 0.32 | 0.00 | 1.00 | 0.50 |
| 0.34 | 0.00 | 1.00 | 0.50 |
| 0.36 | 0.00 | 1.00 | 0.50 |
| 0.38 | 0.00 | 1.00 | 0.50 |
| 0.40 | 0.00 | 1.00 | 0.50 |
| 0.42 | 0.00 | 1.00 | 0.50 |
| 0.44 | 0.20 | 1.00 | 0.60 |
| 0.46 | 0.20 | 0.96 | 0.58 |
| 0.48 | 0.40 | 0.96 | 0.68 |
| 0.50 | 0.60 | 0.96 | 0.78 |
| 0.52 | 0.60 | 0.96 | 0.78 ← |
| 0.54 | 0.80 | 0.88 | 0.84 |
| 0.56 | 1.00 | 0.84 | 0.92 |
| 0.58 | 1.00 | 0.80 | 0.90 |
| 0.60 | 1.00 | 0.80 | 0.90 |
| 0.62 | 1.00 | 0.56 | 0.78 |
| 0.64 | 1.00 | 0.24 | 0.62 |
| 0.66 | 1.00 | 0.12 | 0.56 |
| 0.68 | 1.00 | 0.12 | 0.56 |
| 0.70 | 1.00 | 0.00 | 0.50 |

**Recommended `REFUSAL_THRESHOLD`: 0.52** — refuses 60% of off-corpus questions for $0 while passing 96% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 5/5
- False refusals on answerable questions: 4/25
- Citation precision (cited docs ∩ expected docs): 24/24

## LLM-judged answer quality (judge: qwen2.5:7b-instruct)

- Faithfulness (every claim supported by the excerpts): 20/21
- Correctness vs the golden expected answer: 19/21
