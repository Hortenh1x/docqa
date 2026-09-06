# Evaluation results

_Embeddings: text-embedding-3-small@1024 · rerank: none · top-8 after fusion of vector top-100 + FTS top-0_

Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| direct | 142 | 0.95 | 0.597 |
| table | 16 | 0.62 | 0.622 |
| multi_doc | 80 | 0.82 | 0.614 |
| version | 52 | 0.94 | 0.585 |
| version_history | 24 | 0.79 | 0.552 |
| buried | 6 | 1.00 | 0.546 |
| distractor_country | 84 | 1.00 | 0.643 |
| stale_faq | 6 | 0.67 | 0.550 |
| as_of_date | 12 | 0.67 | 0.501 |
| german | 78 | 1.00 | 0.643 |
| no_answer | 136 | — | 0.456 |
| access | 90 | — | 0.457 |
| partial | 12 | 1.00 | 0.562 |
| **all answerable** | 512 | **0.92** | |

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
| 0.44 | 0.46 | 0.99 | 0.73 |
| 0.46 | 0.57 | 0.97 | 0.77 |
| 0.48 | 0.65 | 0.95 | 0.80 ← |
| 0.50 | 0.76 | 0.92 | 0.84 |
| 0.52 | 0.81 | 0.87 | 0.84 |
| 0.54 | 0.87 | 0.80 | 0.84 |
| 0.56 | 0.92 | 0.74 | 0.83 |
| 0.58 | 0.94 | 0.64 | 0.79 |
| 0.60 | 0.97 | 0.54 | 0.76 |
| 0.62 | 0.99 | 0.44 | 0.72 |
| 0.64 | 0.99 | 0.32 | 0.65 |
| 0.66 | 1.00 | 0.25 | 0.62 |
| 0.68 | 1.00 | 0.18 | 0.59 |
| 0.70 | 1.00 | 0.10 | 0.55 |

**Recommended `REFUSAL_THRESHOLD`: 0.48** — refuses 65% of off-corpus questions for $0 while passing 95% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer

_Not run yet (needs a configured LLM): `uv run python -m eval.run_eval --collection <id> --with-answers --api-key <key>`._

## Access control

- Restricted questions (asked under a role that may not see all of the answer): 102
- Retrieval leaks (a chunk outside the role's labels surfaced): 0/102
- Reveal hint names the unlocking label: 95/102

## Misses

- `v0038` [version] expected ['POL-005-v4.1'], top-8: ['SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'POL-023-v2.0']
- `v0039` [version] expected ['POL-005-v4.1'], top-8: ['SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'POL-005-v3.0', 'SEC-STD-PASSWORD']
- `s0040` [stale_faq] expected ['POL-005-v4.1'], top-8: ['SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'POL-005-v3.0', 'SEC-STD-PASSWORD']
- `h0041` [version_history] expected ['POL-005-v3.0'], top-8: ['FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'FAQ-004', 'POL-023-v2.0']
- `h0042` [version_history] expected ['POL-005-v3.0'], top-8: ['FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD']
- `t0044` [table] expected ['POL-006-v2.2'], top-8: ['POL-006-DE', 'FAQ-008', 'POL-006-v1.0', 'FAQ-008-DE', 'FAQ-008', 'EXEC-COMP', 'FAQ-005', 'ENG-RFC-02']
- `d0064` [direct] expected ['POL-008-v2.1'], top-8: ['HR-PARENTS', 'POL-001-DE', 'POL-001-v2.3', 'POL-008-DE', 'POL-001-v1.0', 'POL-001-v2.0', 'HR-PARENTS', 'HR-LEAVE']
- `h0077` [version_history] expected ['POL-011-v1.5'], top-8: ['POL-012-v1.0', 'FIN-RATES-2025', 'FIN-RATES-2026', 'EXEC-COMP', 'POL-012-v0.9', 'FIN-RATES-2024', 'FIN-RATES-2023', 'HB-S-DE']
- `v0087` [version] expected ['POL-013-v2.0'], top-8: ['POL-001-v1.0', 'POL-013-v1.5', 'POL-013-DE', 'POL-013-DE', 'POL-013-v1.0', 'FAQ-006', 'POL-001-v2.0', 'POL-013-v1.5']
- `s0088` [stale_faq] expected ['POL-013-v2.0'], top-8: ['POL-001-v1.0', 'POL-013-v1.5', 'POL-013-DE', 'POL-013-DE', 'POL-013-v1.0', 'FAQ-006', 'POL-001-v2.0', 'POL-013-v1.5']
- `h0090` [version_history] expected ['POL-013-v1.5'], top-8: ['POL-014-v1.0', 'POL-001-v1.0', 'POL-003-v1.0', 'POL-001-v2.3', 'POL-013-DE', 'POL-013-DE', 'FAQ-006', 'FAQ-006']
- `h0092` [version_history] expected ['POL-013-v1.0'], top-8: ['POL-001-v1.0', 'POL-001-DE', 'HR-LEAVE', 'POL-001-v2.0', 'POL-001-v2.3', 'HB-ES', 'FAQ-009', 'POL-001-v1.0']
- `d0292` [direct] expected ['FIN-RATES-2025'], top-8: ['FIN-RATES-2026', 'POL-004-DE', 'FIN-RATES-2024', 'FIN-RATES-2023', 'POL-004-v3.0', 'POL-004-v2.0', 'HB-S-FR', 'POL-004-v2.0']
- `t0297` [table] expected ['FIN-RATES-2026'], top-8: ['HB-S-ES', 'HB-S-PT', 'HB-S-UK', 'POL-004-v3.0', 'POL-004-v2.0', 'POL-004-DE', 'HB-S-FR', 'HB-S-FR']
- `t0298` [table] expected ['FIN-RATES-2026'], top-8: ['HB-S-ES', 'POL-004-DE', 'POL-004-v3.0', 'FIN-RATES-2025', 'FIN-RATES-2024', 'HB-ES', 'HB-S-PT', 'POL-004-v2.0']
- `t0299` [table] expected ['FIN-RATES-2026'], top-8: ['HB-S-PL', 'FIN-RATES-2025', 'HB-S-DE', 'FIN-RATES-2023', 'POL-019-v0.9', 'HB-S-PT', 'HB-S-FR', 'POL-004-DE']
- `t0302` [table] expected ['FIN-RATES-2026'], top-8: ['HB-S-FR', 'HB-S-FR', 'FIN-RATES-2025', 'HB-FR', 'POL-004-DE', 'FIN-RATES-2023', 'FIN-RATES-2024', 'HB-S-UK']
- `t0303` [table] expected ['FIN-RATES-2026'], top-8: ['HB-S-UK', 'HB-S-UK', 'HB-S-DE', 'HB-S-FR', 'POL-019-v0.9', 'HB-S-FR', 'FIN-RATES-2025', 'FAQ-011']
- `d0428` [direct] expected ['OPS-VISITORS'], top-8: ['HB-DE', 'HB-UK', 'HR-PARENTS', 'SEC-STD-LOGGING', 'SEC-RB-OFFB', 'HR-OFFB', 'HB-UK', 'HB-FR']
- `d0433` [direct] expected ['EXEC-AH-06'], top-8: ['FAQ-014', 'FAQ-013', 'FAQ-014-DE', 'HB-PT', 'HB-UK', 'FAQ-013-DE', 'HB-UK', 'POL-013-v1.0']
- `d0434` [direct] expected ['EXEC-AH-06'], top-8: ['ENG-TEAM-02', 'ENG-TEAM-04', 'EXEC-AH-02', 'POL-002-v2.0', 'POL-013-v2.0', 'EXEC-BOARD-04', 'EXEC-BOARD-02', 'HR-WELLBEING']
- `d0435` [direct] expected ['EXEC-AH-04'], top-8: ['MTG-12', 'MTG-28', 'MTG-20', 'MTG-04', 'EXEC-BOARD-04', 'EXEC-BOARD-01', 'EXEC-BOARD-04', 'POL-025-v1.0']
- `d0436` [direct] expected ['EXEC-AH-04'], top-8: ['POL-025-v1.0', 'POL-025-v1.5', 'SEC-PM-05', 'EXEC-BOARD-01', 'EXEC-BOARD-04', 'EXEC-BOARD-02', 'MTG-28', 'POL-025-v2.0']
- `m0512` [as_of_date] expected ['MTG-02'], top-8: ['POL-013-v1.5', 'ENG-GUIDE-ONCALL', 'ENG-GUIDE-ONCALL', 'POL-013-v1.5', 'FAQ-006', 'POL-013-v1.5', 'POL-013-v1.0', 'FAQ-006']
- `m0514` [as_of_date] expected ['MTG-03'], top-8: ['MTG-26', 'MTG-18', 'MTG-02', 'POL-020-v1.0', 'MTG-10', 'MTG-05', 'MTG-01', 'POL-020-v1.1']
- `m0516` [as_of_date] expected ['MTG-04'], top-8: ['POL-020-v1.0', 'POL-020-v1.1', 'POL-020-v1.0', 'POL-020-v1.1', 'POL-020-v1.0', 'POL-020-v1.0', 'POL-020-v1.1', 'POL-013-v1.5']
- `m0520` [as_of_date] expected ['MTG-06'], top-8: ['MTG-17', 'SEC-STD-ENDPOINT', 'SEC-PM-04', 'PUB-RELEASE', 'ENG-GUIDE-RELEASE', 'MTG-05', 'ENG-GUIDE-RELEASE', 'ENG-ADR-04']
- `x0523` [multi_doc] expected ['POL-002-v2.0', 'POL-003-v1.1'], top-8: ['POL-003-v1.0', 'POL-003-v1.1', 'POL-003-v1.1', 'POL-003-v1.0', 'POL-002-v1.0', 'POL-003-DE', 'POL-003-DE', 'FAQ-016']
- `x0524` [multi_doc] expected ['POL-002-v2.0', 'POL-003-v1.1'], top-8: ['POL-003-v1.0', 'POL-003-v1.1', 'FAQ-016', 'POL-002-v1.0', 'POL-003-DE', 'POL-003-v1.1', 'FAQ-016-DE', 'FAQ-002']
- `x0526` [multi_doc] expected ['FIN-RATES-2026', 'POL-004-v3.0'], top-8: ['HB-S-UK', 'FIN-RATES-2025', 'FIN-RATES-2024', 'FIN-RATES-2023', 'FIN-RATES-2026', 'HB-S-UK', 'FIN-RATES-2026', 'HB-S-DE']
- `x0527` [multi_doc] expected ['POL-006-v2.2', 'POL-012-v1.0'], top-8: ['POL-012-v1.0', 'POL-012-v0.9', 'FAQ-008', 'POL-012-v0.9', 'POL-012-v0.9', 'POL-012-DE', 'POL-006-v1.0', 'POL-006-DE']
- `x0528` [multi_doc] expected ['POL-006-v2.2', 'POL-012-v1.0'], top-8: ['POL-012-v1.0', 'POL-012-v0.9', 'POL-012-v0.9', 'FAQ-008', 'POL-012-DE', 'POL-006-DE', 'POL-006-v1.0', 'POL-012-v0.9']
- `x0535` [multi_doc] expected ['POL-011-v2.0', 'POL-025-v2.0'], top-8: ['POL-011-v1.0', 'POL-011-v2.0', 'FAQ-005', 'EXEC-COMP', 'POL-011-v1.5', 'POL-011-v1.5', 'FAQ-005', 'POL-011-v2.0']
- `x0546` [multi_doc] expected ['POL-007-v1.2', 'HB-PT'], top-8: ['POL-007-v1.2', 'POL-007-v1.0', 'POL-007-v1.0', 'HB-ES', 'POL-007-DE', 'FAQ-009', 'HB-FR', 'POL-007-v1.0']
- `x0566` [multi_doc] expected ['POL-006-v2.2', 'HR-ONB-01'], top-8: ['ENG-RFC-02', 'POL-006-DE', 'ENG-RFC-02', 'POL-017-v1.0', 'ENG-TEAM-01', 'POL-018-v1.2', 'ENG-RFC-02', 'HR-ONB-01']
- `x0574` [multi_doc] expected ['POL-006-v2.2', 'HR-ONB-03'], top-8: ['POL-018-v1.2', 'POL-006-v1.0', 'FAQ-008', 'ENG-ADR-04', 'POL-006-DE', 'POL-006-v2.2', 'POL-017-v1.0', 'ENG-ADR-04']
- `x0582` [multi_doc] expected ['POL-006-v2.2', 'HR-ONB-05'], top-8: ['FAQ-008', 'POL-006-v1.0', 'POL-006-v2.2', 'POL-006-DE', 'FAQ-008-DE', 'FAQ-008', 'POL-006-v1.0', 'HR-ONB-02']
- `x0585` [multi_doc] expected ['POL-008-v2.1', 'HR-LEAVE'], top-8: ['POL-001-v2.0', 'POL-001-v2.3', 'POL-008-v2.1', 'POL-001-v1.0', 'HR-PARENTS', 'FAQ-010', 'POL-001-v2.3', 'FAQ-010']
- `x0586` [multi_doc] expected ['POL-008-v2.1', 'HR-LEAVE'], top-8: ['HR-PARENTS', 'POL-001-v1.0', 'FAQ-010', 'POL-001-v2.3', 'POL-001-v2.0', 'POL-008-v2.1', 'HR-PARENTS', 'POL-001-v2.3']
- `x0595` [multi_doc] expected ['POL-005-v4.1', 'SEC-STD-PASSWORD'], top-8: ['SEC-STD-PASSWORD', 'FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'POL-023-v2.0']
- `x0596` [multi_doc] expected ['POL-005-v4.1', 'SEC-STD-PASSWORD'], top-8: ['SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'FAQ-004', 'FAQ-004', 'SEC-STD-PASSWORD', 'SEC-STD-PASSWORD', 'POL-023-v2.0']
