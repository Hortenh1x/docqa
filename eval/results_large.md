# Evaluation results — large set (447 questions)

_Embeddings: bge-m3 · rerank: none · top-8 after fusion of vector top-30 + FTS top-30 · LLM: deepseek-v4-flash_

Golden set: `eval/golden_large.yaml` — 447 EN questions: direct(167) table(40) multi_doc(40) version(30) buried(20) no_answer(150).

Reproduce:
`uv run python -m eval.run_eval --collection <policies-en id> --golden eval/golden_large.yaml --results eval/results_large.md --with-answers --judge --judge-model deepseek-chat --concurrency 4 --api-key <key>`
(judge-model `deepseek-chat` = the non-thinking alias of v4-flash, same price — see the judge section for why this matters)

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| direct | 167 | 0.99 | 0.578 |
| table | 40 | 0.97 | 0.577 |
| multi_doc | 40 | 0.97 | 0.607 |
| version | 30 | 1.00 | 0.572 |
| buried | 20 | 1.00 | 0.578 |
| no_answer | 150 | — | 0.509 |
| **all answerable** | 297 | **0.99** | |

## Refusal threshold sweep (gate score = best vector cosine, rerank=none)

| Threshold | Refuses no_answer | Passes answerable | Balanced |
| --- | --- | --- | --- |
| 0.30 | 0.00 | 1.00 | 0.50 |
| 0.32 | 0.00 | 1.00 | 0.50 |
| 0.34 | 0.00 | 1.00 | 0.50 |
| 0.36 | 0.00 | 1.00 | 0.50 |
| 0.38 | 0.01 | 1.00 | 0.50 |
| 0.40 | 0.01 | 1.00 | 0.50 |
| 0.42 | 0.03 | 1.00 | 0.51 |
| 0.44 | 0.09 | 1.00 | 0.54 |
| 0.46 | 0.20 | 0.99 | 0.59 |
| 0.48 | 0.31 | 0.97 | 0.64 ← |
| 0.50 | 0.44 | 0.95 | 0.69 |
| 0.52 | 0.59 | 0.88 | 0.73 |
| 0.54 | 0.70 | 0.79 | 0.75 |
| 0.56 | 0.81 | 0.67 | 0.74 |
| 0.58 | 0.90 | 0.51 | 0.71 |
| 0.60 | 0.97 | 0.36 | 0.67 |
| 0.62 | 0.99 | 0.23 | 0.61 |
| 0.64 | 0.99 | 0.11 | 0.55 |
| 0.66 | 1.00 | 0.05 | 0.52 |
| 0.68 | 1.00 | 0.02 | 0.51 |
| 0.70 | 1.00 | 0.01 | 0.51 |

**Recommended `REFUSAL_THRESHOLD`: 0.48** — refuses 31% of off-corpus questions for $0 while passing 97% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 149/150
  - the single "miss" (n002) is an **empty answer with refused=false**, not an invented
    one — zero hallucinated answers across all 150 off-corpus questions
- False refusals on answerable questions: 18/297
  - 15/18 are $0 retrieval-gate refusals with scores 0.442–0.500, i.e. just under the
    0.50 threshold (soft-fact/communication questions with weak embedding similarity);
    3/18 are NO_ANSWER sentinel calls (d087 after a retrieval miss; t014/t015 chose to
    refuse "Netherlands/Japan per-diem" instead of explaining the ask-finance rule)
- Citation precision (cited docs ∩ expected docs): 281/282
- Reliability: 2/447 responses came back **empty** (completion hit the 1024-token cap
  on one, 0 tokens on the other) — deepseek-v4-flash sporadically burns the entire
  completion budget on hidden reasoning. Pin the non-thinking mode for this pipeline
  (`deepseek-chat` alias or `thinking: {"type": "disabled"}`).

## LLM-judged answer quality (judge: deepseek-chat, non-thinking v4-flash)

- Faithfulness (every claim supported by the excerpts): **278/278 (100%)**
- Correctness vs the golden expected answer: **272/278 (97.8%)**
- All 6 correctness fails are faithful-but-incomplete answers (a secondary key fact
  dropped: d051, d064, d071, m025; over-hedging: m038) or retrieval-caused (m040 —
  POL-004 missing from top-8, so the 30-day deadline never reached the model).
- Note: the first judge pass ran on `deepseek-v4-flash` with max_tokens=200 and scored
  186/278 — that number is an artifact, not a measurement: the model non-deterministically
  spends the whole completion budget on hidden reasoning, returns empty content, and the
  parser correctly counts an absent verdict as a fail. Re-judged from the same recorded
  answers with the non-thinking `deepseek-chat` (same underlying model/price): 0 empty
  verdicts.

## Misses

- `d087` [direct] expected ['POL-009'], top-8: ['POL-003', 'POL-008', 'POL-007', 'POL-002', 'HR-002', 'HR-004', 'POL-004', 'OPS-001']
- `t037` [table] expected ['HR-001'], top-8: ['POL-002', 'OPS-001', 'POL-008', 'POL-002', 'POL-005', 'POL-003', 'POL-006', 'POL-007']
- `m040` [multi_doc] expected ['HR-002', 'POL-004'], top-8: ['HR-002', 'POL-006', 'POL-008', 'POL-006', 'OPS-001', 'POL-001-v1', 'POL-001-v2', 'HR-004']
