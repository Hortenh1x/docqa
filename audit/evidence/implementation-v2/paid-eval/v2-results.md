# Evaluation results

_Isolated synthetic snapshot; deepseek-v4-flash (provider aliases to V4.1); OpenAI embeddings@1024; gate=0.28; top_n=20; actual trimmed context; judge=gpt-4.1-mini_

Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`

## Retrieval quality by category

| Category | Questions | Recall@20 | Mean gate score |
| --- | --- | --- | --- |
| direct | 5 | 1.00 | 0.621 |
| table | 5 | 1.00 | 0.573 |
| multi_doc | 5 | 0.80 | 0.674 |
| version | 5 | 1.00 | 0.623 |
| version_history | 5 | 1.00 | 0.503 |
| buried | 5 | 1.00 | 0.515 |
| distractor_country | 5 | 1.00 | 0.640 |
| stale_faq | 5 | 1.00 | 0.552 |
| as_of_date | 5 | 0.80 | 0.507 |
| german | 5 | 1.00 | 0.641 |
| no_answer | 5 | — | 0.460 |
| access | 5 | 1.00 | 0.498 |
| partial | 5 | 1.00 | 0.544 |
| **all answerable** | 57 | **0.96** | |

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
| 0.38 | 0.12 | 1.00 | 0.56 |
| 0.40 | 0.25 | 1.00 | 0.62 |
| 0.42 | 0.25 | 1.00 | 0.62 |
| 0.44 | 0.38 | 1.00 | 0.69 |
| 0.46 | 0.50 | 0.98 | 0.74 ← |
| 0.48 | 0.62 | 0.91 | 0.77 |
| 0.50 | 0.88 | 0.82 | 0.85 |
| 0.52 | 0.88 | 0.75 | 0.81 |
| 0.54 | 0.88 | 0.63 | 0.75 |
| 0.56 | 1.00 | 0.54 | 0.77 |
| 0.58 | 1.00 | 0.42 | 0.71 |
| 0.60 | 1.00 | 0.39 | 0.69 |
| 0.62 | 1.00 | 0.30 | 0.65 |
| 0.64 | 1.00 | 0.25 | 0.62 |
| 0.66 | 1.00 | 0.18 | 0.59 |
| 0.68 | 1.00 | 0.16 | 0.58 |
| 0.70 | 1.00 | 0.09 | 0.54 |

**Recommended `REFUSAL_THRESHOLD`: 0.46** — refuses 50% of off-corpus questions for $0 while passing 98% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 8/8
- False refusals on answerable questions: 2/57
- Citation precision (cited docs ∩ expected docs): 56/57

## LLM-judged answer quality (judge: gpt-4.1-mini)

- Faithfulness (every claim supported by the excerpts): 53/55
- Correctness vs the golden expected answer: 53/55

## Access control

- Restricted questions (asked under a role that may not see all of the answer): 8
- Retrieval leaks (a chunk outside the role's labels surfaced): 0/8
- Reveal hint names the unlocking label: 6/8
- Restricted values appearing in an answer (the real leak test): 0/3
- Answered from open content instead of refusing: 0/3
- Unlock questions (asked under the right role), recall@20: 2/2

## Misses

- `m0520` [as_of_date] expected ['MTG-06'], top-20: ['SEC-STD-ENDPOINT', 'PUB-RELEASE', 'ENG-GUIDE-RELEASE', 'MTG-05', 'ENG-GUIDE-RELEASE', 'ENG-ADR-04', 'MTG-03', 'PUB-SLA', 'MTG-17', 'MTG-27', 'MTG-17', 'MTG-27', 'ENG-TEAM-03', 'ENG-RFC-09', 'MTG-02', 'ENG-ADR-06', 'POL-013-v1.5', 'ENG-ADR-04', 'MTG-19', 'ENG-ADR-03']
- `x0533` [multi_doc] expected ['POL-006-v2.2', 'POL-023-v2.0'], top-20: ['POL-006-v1.0', 'POL-006-v2.2', 'POL-006-v2.2', 'FAQ-008', 'POL-006-DE', 'POL-006-DE', 'FAQ-008', 'SEC-RB-LOSTDEVICE', 'POL-006-v1.0', 'FAQ-008-DE', 'POL-006-v1.0', 'POL-006-v2.2', 'HR-OFFB', 'SEC-STD-BACKUP', 'FAQ-014', 'POL-006-DE', 'HR-OFFB', 'POL-006-v2.2', 'POL-023-v1.0', 'SEC-RB-LOSTDEVICE']
