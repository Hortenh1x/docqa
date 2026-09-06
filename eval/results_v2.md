# Evaluation results

_Embeddings: text-embedding-3-small@1024 · rerank: none · top-20 after fusion of vector top-100 + FTS top-100 · LLM: deepseek-v4-flash_

Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`

## Retrieval quality by category

| Category | Questions | Recall@20 | Mean gate score |
| --- | --- | --- | --- |
| direct | 142 | 0.97 | 0.597 |
| table | 16 | 1.00 | 0.622 |
| multi_doc | 80 | 0.99 | 0.614 |
| version | 52 | 1.00 | 0.585 |
| version_history | 24 | 0.96 | 0.552 |
| buried | 6 | 1.00 | 0.546 |
| distractor_country | 84 | 1.00 | 0.643 |
| stale_faq | 6 | 1.00 | 0.550 |
| as_of_date | 12 | 0.92 | 0.501 |
| german | 78 | 1.00 | 0.643 |
| no_answer | 136 | — | 0.456 |
| access | 180 | 1.00 | 0.513 |
| partial | 12 | 1.00 | 0.562 |
| **all answerable** | 602 | **0.99** | |

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
| 0.32 | 0.01 | 1.00 | 0.50 |
| 0.34 | 0.03 | 1.00 | 0.52 |
| 0.36 | 0.04 | 1.00 | 0.52 |
| 0.38 | 0.12 | 1.00 | 0.56 |
| 0.40 | 0.20 | 1.00 | 0.60 |
| 0.42 | 0.34 | 0.99 | 0.67 |
| 0.44 | 0.46 | 0.99 | 0.72 |
| 0.46 | 0.57 | 0.97 | 0.77 ← |
| 0.48 | 0.65 | 0.95 | 0.80 |
| 0.50 | 0.76 | 0.92 | 0.84 |
| 0.52 | 0.81 | 0.86 | 0.83 |
| 0.54 | 0.87 | 0.79 | 0.83 |
| 0.56 | 0.92 | 0.71 | 0.82 |
| 0.58 | 0.94 | 0.61 | 0.77 |
| 0.60 | 0.97 | 0.51 | 0.74 |
| 0.62 | 0.99 | 0.41 | 0.70 |
| 0.64 | 0.99 | 0.30 | 0.64 |
| 0.66 | 1.00 | 0.22 | 0.61 |
| 0.68 | 1.00 | 0.16 | 0.58 |
| 0.70 | 1.00 | 0.09 | 0.54 |

**Recommended `REFUSAL_THRESHOLD`: 0.46** — refuses 57% of off-corpus questions for $0 while passing 97% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 190/226
- False refusals on answerable questions: 20/602
- Citation precision (cited docs ∩ expected docs): 596/602

## LLM-judged answer quality (judge: deepseek-chat)

- Faithfulness (every claim supported by the excerpts): 580/582
- Correctness vs the golden expected answer: 570/582
- Off-corpus questions answered instead of refused: 36 — of which unfaithful (claims not supported by the excerpts): 1

## Access control

- Restricted questions (asked under a role that may not see all of the answer): 102
- Retrieval leaks (a chunk outside the role's labels surfaced): 0/102
- Reveal hint names the unlocking label: 95/102
- Restricted values appearing in an answer (the real leak test): 0/90
- Answered from open content instead of refusing: 6/90
- Unlock questions (asked under the right role), recall@20: 90/90

## Misses

- `h0092` [version_history] expected ['POL-013-v1.0'], first 8 of top-20: ['POL-001-v1.0', 'POL-001-DE', 'HR-LEAVE', 'POL-001-v2.0', 'POL-001-v2.3', 'HB-ES', 'FAQ-009', 'POL-001-v1.0']
- `d0433` [direct] expected ['EXEC-AH-06'], first 8 of top-20: ['FAQ-014', 'FAQ-013', 'FAQ-014-DE', 'HB-PT', 'HB-UK', 'FAQ-013-DE', 'HB-UK', 'POL-013-v1.0']
- `d0434` [direct] expected ['EXEC-AH-06'], first 8 of top-20: ['ENG-TEAM-02', 'ENG-TEAM-04', 'EXEC-AH-02', 'POL-002-v2.0', 'POL-013-v2.0', 'EXEC-BOARD-04', 'EXEC-BOARD-02', 'HR-WELLBEING']
- `d0435` [direct] expected ['EXEC-AH-04'], first 8 of top-20: ['MTG-12', 'MTG-28', 'MTG-20', 'MTG-04', 'EXEC-BOARD-04', 'EXEC-BOARD-01', 'EXEC-BOARD-04', 'POL-025-v1.0']
- `d0436` [direct] expected ['EXEC-AH-04'], first 8 of top-20: ['POL-025-v1.0', 'POL-025-v1.5', 'SEC-PM-05', 'EXEC-BOARD-01', 'EXEC-BOARD-04', 'EXEC-BOARD-02', 'MTG-28', 'POL-025-v2.0']
- `m0520` [as_of_date] expected ['MTG-06'], first 8 of top-20: ['MTG-17', 'SEC-STD-ENDPOINT', 'SEC-PM-04', 'PUB-RELEASE', 'ENG-GUIDE-RELEASE', 'MTG-05', 'ENG-GUIDE-RELEASE', 'ENG-ADR-04']
- `x0574` [multi_doc] expected ['POL-006-v2.2', 'HR-ONB-03'], first 8 of top-20: ['POL-018-v1.2', 'POL-006-v1.0', 'FAQ-008', 'ENG-ADR-04', 'POL-006-DE', 'POL-006-v2.2', 'POL-017-v1.0', 'ENG-ADR-04']
