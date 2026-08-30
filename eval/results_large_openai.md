# Evaluation results — large set on OpenAI embeddings

_Embeddings: text-embedding-3-small@1024 · rerank: none · top-8 after fusion of vector top-30 + FTS top-30 · LLM: deepseek-v4-flash (thinking allowed, max_tokens 4096) · judge: deepseek-chat_

The run was executed with the retrieval gate OFF (`REFUSAL_THRESHOLD=0.01`) so that every
question records its gate score and a sentinel-only refusal outcome; end-to-end behavior
at any threshold is then computed post-hoc (section at the bottom).

Reproduce:
`EMBEDDING_PROVIDER=openai REFUSAL_THRESHOLD=0.01 uv run python -m eval.run_eval --collection <openai policies-en id> --golden eval/golden_large.yaml --results eval/results_large_openai.md --with-answers --judge --judge-model deepseek-chat --concurrency 4 --api-key <key>`

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| direct | 167 | 0.99 | 0.458 |
| table | 40 | 0.95 | 0.453 |
| multi_doc | 40 | 0.97 | 0.558 |
| version | 30 | 1.00 | 0.481 |
| buried | 20 | 1.00 | 0.556 |
| no_answer | 150 | — | 0.377 |
| **all answerable** | 297 | **0.99** | |

## Refusal threshold sweep (gate score = best vector cosine, rerank=none)

| Threshold | Refuses no_answer | Passes answerable | Balanced |
| --- | --- | --- | --- |
| 0.10 | 0.00 | 1.00 | 0.50 |
| 0.12 | 0.00 | 1.00 | 0.50 |
| 0.14 | 0.00 | 1.00 | 0.50 |
| 0.16 | 0.00 | 1.00 | 0.50 |
| 0.18 | 0.00 | 1.00 | 0.50 |
| 0.20 | 0.00 | 1.00 | 0.50 |
| 0.22 | 0.01 | 1.00 | 0.51 |
| 0.24 | 0.02 | 1.00 | 0.51 |
| 0.26 | 0.07 | 0.99 | 0.53 |
| 0.28 | 0.09 | 0.98 | 0.54 |
| 0.30 | 0.19 | 0.97 | 0.58 ← |
| 0.32 | 0.27 | 0.95 | 0.61 |
| 0.34 | 0.35 | 0.93 | 0.64 |
| 0.36 | 0.42 | 0.91 | 0.66 |
| 0.38 | 0.51 | 0.86 | 0.69 |
| 0.40 | 0.60 | 0.82 | 0.71 |
| 0.42 | 0.67 | 0.75 | 0.71 |
| 0.44 | 0.75 | 0.67 | 0.71 |
| 0.46 | 0.84 | 0.60 | 0.72 |
| 0.48 | 0.90 | 0.49 | 0.70 |
| 0.50 | 0.95 | 0.41 | 0.68 |
| 0.52 | 0.98 | 0.32 | 0.65 |
| 0.54 | 1.00 | 0.24 | 0.62 |
| 0.56 | 1.00 | 0.19 | 0.59 |
| 0.58 | 1.00 | 0.16 | 0.58 |
| 0.60 | 1.00 | 0.11 | 0.56 |
| 0.62 | 1.00 | 0.07 | 0.54 |
| 0.64 | 1.00 | 0.03 | 0.52 |
| 0.66 | 1.00 | 0.02 | 0.51 |
| 0.68 | 1.00 | 0.02 | 0.51 |
| 0.70 | 1.00 | 0.01 | 0.50 |

**Recommended `REFUSAL_THRESHOLD`: 0.30** — refuses 19% of off-corpus questions for $0 while passing 97% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 149/150
- False refusals on answerable questions: 5/297
- Citation precision (cited docs ∩ expected docs): 294/297

## LLM-judged answer quality (judge: deepseek-chat)

- Faithfulness (every claim supported by the excerpts): 292/292
- Correctness vs the golden expected answer: 287/292

## Misses

- `d020` [direct] expected ['POL-002'], top-8: ['OPS-001', 'SEC-001', 'FIN-001', 'HR-003', 'HR-002', 'POL-009', 'OPS-001', 'POL-003']
- `t037` [table] expected ['HR-001'], top-8: ['POL-002', 'POL-005', 'HR-004', 'POL-010', 'POL-006', 'OPS-001', 'POL-002', 'POL-004']
- `t038` [table] expected ['HR-001'], top-8: ['POL-005', 'OPS-001', 'OPS-001', 'HR-002', 'POL-005', 'HR-002', 'POL-006', 'POL-010']
- `m025` [multi_doc] expected ['OPS-001', 'SEC-001'], top-8: ['OPS-001', 'POL-006', 'OPS-001', 'POL-002', 'POL-005', 'POL-009', 'HR-001', 'POL-005']

## Post-hoc threshold analysis (e2e = gate ∪ sentinel)

With the gate off, the NO_ANSWER sentinel alone refused 149/150 off-corpus questions
with only 5/297 false refusals — the gate's remaining job is saving the cost of an LLM
call on obvious junk, so the threshold should be biased toward user experience:

| Threshold | Gate refuses no_answer ($0) | e2e refuses no_answer | e2e false refusals | Gate passes answerable |
| --- | --- | --- | --- | --- |
| 0.24 | 0.02 | 0.99 | 2.0% | 99.7% |
| 0.26 | 0.07 | 0.99 | 3.0% | 98.7% |
| **0.28** | **0.09** | **0.99** | **3.7%** | **98.0%** |
| 0.30 | 0.19 | 1.00 | 5.1% | 96.6% |
| 0.32 | 0.27 | 1.00 | 6.7% | 94.6% |

**Deploy recommendation: `REFUSAL_THRESHOLD=0.28`** (the harness's own ≥0.95-pass rule
says 0.30; 0.28 trades 10% of free gate refusals for ~1.4pp fewer false refusals —
the sentinel covers the difference at ~$0.0005/query). Anything in 0.24–0.30 is sane.
Score separation: answerable mean 0.480 (min 0.221) vs no_answer mean 0.377 (max 0.530).

Notes on the residual failures:

- The 1/150 non-refused off-corpus question (n114, "Is there a daily lunch subsidy?")
  produced a **correct grounded negative** ("no separate subsidy; per-diem covers meals",
  cited to FIN-001) — not an invented benefit. Zero hallucinations across all 447.
- The 5 sentinel false refusals (d020, t014, m009, v025, v029) are conservatism on
  paraphrase-heavy or meta questions; d020 also lost retrieval (its doc missed top-8).
- Correctness misses (5/292) are faithful-but-incomplete answers, same shape as the
  bge-m3 run.

Answer-layer spend for the full run: 447 LLM calls, $0.171 recorded (1.11M prompt +
56k completion tokens); judge ≈ $0.11; OpenAI embeddings (corpus + 447 queries) < $0.001.
