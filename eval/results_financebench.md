# Evaluation results — FinanceBench (real 10-K/10-Q filings)

_Corpus: 334 SEC filings (Apache-2.0, github.com/patronus-ai/financebench) · embeddings text-embedding-3-small@1024 · rerank: none · LLM deepseek-v4-flash · judge deepseek-chat_

Golden set: `eval/golden_financebench.yaml` — 140 of the 150 expert-written questions
(10 dropped with the filings that exceed the 300-page / 25 MB ingestion limits). There
are **no `no_answer` questions** here: every question is answerable, so the refusal
column reads as "how often did the pipeline give up", not "how well did it reject junk".

Reproduce (no API needed — `--direct` runs the pipeline in-process):
`python -m eval.run_eval --collection <financial-filings id> --golden eval/golden_financebench.yaml --results eval/results_financebench.md --with-answers --judge --judge-model deepseek-chat --direct --concurrency 4`

## Retrieval quality by category

| Category | Questions | Recall@20 | Mean gate score |
| --- | --- | --- | --- |
| direct | 95 | 0.89 | 0.681 |
| table | 45 | 0.87 | 0.646 |
| **all answerable** | 140 | **0.89** | |

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
| 0.38 | 0.00 | 1.00 | 0.50 |
| 0.40 | 0.00 | 1.00 | 0.50 |
| 0.42 | 0.00 | 1.00 | 0.50 |
| 0.44 | 0.00 | 1.00 | 0.50 |
| 0.46 | 0.00 | 1.00 | 0.50 |
| 0.48 | 0.00 | 1.00 | 0.50 |
| 0.50 | 0.00 | 1.00 | 0.50 |
| 0.52 | 0.00 | 1.00 | 0.50 |
| 0.54 | 0.00 | 1.00 | 0.50 |
| 0.56 | 0.00 | 1.00 | 0.50 |
| 0.58 | 0.00 | 0.99 | 0.49 |
| 0.60 | 0.00 | 0.95 | 0.47 ← |
| 0.62 | 0.00 | 0.82 | 0.41 |
| 0.64 | 0.00 | 0.73 | 0.36 |
| 0.66 | 0.00 | 0.54 | 0.27 |
| 0.68 | 0.00 | 0.40 | 0.20 |
| 0.70 | 0.00 | 0.28 | 0.14 |

**Recommended `REFUSAL_THRESHOLD`: 0.60** — refuses 0% of off-corpus questions for $0 while passing 95% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 0/0
- False refusals on answerable questions: 70/140
- Citation precision (cited docs ∩ expected docs): 123/140

## LLM-judged answer quality (judge: deepseek-chat)

- Faithfulness (every claim supported by the excerpts): 68/70
- Correctness vs the golden expected answer: 61/70

## Reading the numbers

| Metric | Before widening | After widening |
| --- | --- | --- |
| Recall (expected filing among the retrieved chunks' documents) | 0.70 @8 | **0.89 @20** |
| Citation precision (cited document ∈ expected) | 96/139 (69%) | **123/140 (88%)** |
| Faithfulness — every claim backed by the excerpts (LLM-judged) | 56/56 (100%) | 68/70 (97%) |
| Correctness vs the expert answer (LLM-judged) | 47/56 (84%) | **61/70 (87%)** |
| Gave up instead of answering | 83/139 (60%) | **70/140 (50%)** |

The pipeline still refuses half of these questions, and the honest reason is that this
is a hard benchmark for retrieval, not that the model is timid. Sampling 25 refusals
and checking whether the answer was actually in front of the model:

| Why it refused | Share |
| --- | --- |
| The expected filing never made the window | 4/25 (16%) |
| Right filing, but the answering passage was not among the 20 chunks | 15/25 (60%) |
| The value **was** in the context and the model still refused | 6/25 (24%) |

So three quarters of the remaining refusals are a retrieval problem at the *chunk*
level: a 200-page 10-K holds hundreds of table chunks and the one carrying "capital
expenditure, fiscal 2018" does not always rank in the top twenty. Document-level recall
(0.89) flatters what the model actually sees.

What is left to try, in order of expected value: a cross-encoder reranker over the
40-candidate fusion window (`RERANK_PROVIDER=cohere`), and prepending the document
title — company and fiscal year — to each chunk before embedding, which targets the
"right company, wrong year" misses directly. Both are real work rather than settings.

**A negative result worth recording:** the 24% bucket looked like a prompt problem, so
the prompt was amended to explicitly allow arithmetic over retrieved values ("sums,
differences, ratios… this is not guessing"). It did not help — refusals went 70 → 72
and correctness fell 87% → 84%, because the model started computing and getting it
wrong. Reverted.

## Misses

- `fb016` [direct] expected ['AES_2022_10K'], top-20: ['GENERALMILLS_2021_10K', 'GENERALMILLS_2022_10K', 'GENERALMILLS_2022_10K', 'GENERALMILLS_2019_10K', 'GENERALMILLS_2023_10K', '3M_2020_10K', 'GENERALMILLS_2020_10K', 'AMCOR_2021_10K', 'PFIZER_2021_10K', 'PAYPAL_2022_10K', 'GENERALMILLS_2023_10K', 'ORACLE_2022_10K', 'KRAFTHEINZ_2022_10K', 'ORACLE_2023_10K', 'ORACLE_2019_10K', 'JOHNSON_JOHNSON_2021_10K', 'GENERALMILLS_2023_annualreport', '3M_2021_10K', 'AES_2021_10K', 'GENERALMILLS_2022_10K']
- `fb018` [table] expected ['AES_2022_10K'], top-20: ['WALMART_2021_10K', 'WALMART_2024Q1_10Q', 'WALMART_2019_10K', 'WALMART_2023_annualreport', 'WALMART_2023_10K', 'WALMART_2017_10K', 'WALMART_2021_10K', 'WALMART_2022_10K', 'BESTBUY_2023Q4_EARNINGS', 'BESTBUY_2024Q2_EARNINGS', 'WALMART_2020_10K', 'FOOTLOCKER_2023_10K', 'FOOTLOCKER_2023_annualreport', 'WALMART_2015_10K', 'WALMART_2016_10K', 'WALMART_2017_10K', 'FOOTLOCKER_2022_10K', 'WALMART_2021_10K', 'WALMART_2024Q1_10Q', 'WALMART_2020_10K']
- `fb019` [table] expected ['AMAZON_2017_10K'], top-20: ['ORACLE_2016_10K', 'ORACLE_2015_10K', 'SALESFORCE_2024Q2_EARNINGS', 'EBAY_2018_10K', 'ORACLE_2017_10K', 'APPLE_2017_10K', 'SALESFORCE_2024Q1_EARNINGS', 'PAYPAL_2022_10K', 'EBAY_2019_10K', 'APPLE_2022_10K', 'APPLE_2021_10K', 'MICROSOFT_2018_10K', 'PAYPAL_2022_10K', 'CORNING_2020_10K', 'APPLE_2015_10K', 'PAYPAL_2022_10K', 'EBAY_2017_10K', 'BESTBUY_2015_10K', 'APPLE_2018_10K', 'NIKE_2021_10K']
- `fb023` [direct] expected ['AMCOR_2022_8K_dated-2022-07-01'], top-20: ['AMCOR_2022_8K_2022-07-01', 'AMCOR_2022_8K_2022-04-26', 'AMCOR_2023_10K', 'AMCOR_2020_10K', 'AMCOR_2019_10K', 'AMCOR_2019_10K', 'AMCOR_2021_10K', 'AMCOR_2021_10K', 'AMCOR_2022_10K', 'AMCOR_2023_10K', 'AMCOR_2023Q4_EARNINGS', 'AMCOR_2020_10K', 'AMCOR_2022_10K', 'AMCOR_2022_10K', 'AMCOR_2021_10K', 'AMCOR_2023_10K', 'AMCOR_2023_10K', 'AMCOR_2023Q2_10Q', 'AMCOR_2021_10K', 'AMCOR_2022_8K_2022-07-01']
- `fb032` [direct] expected ['AMD_2022_10K'], top-20: ['WALMART_2023_annualreport', 'AMD_2015_10K', 'WALMART_2024Q1_10Q', 'INTEL_2015_10K', 'WALMART_2023_10K', 'CORNING_2022_10K', 'AMD_2015_10K', 'AMD_2017_10K', 'WALMART_2021_10K', 'COCACOLA_2019_10K', 'ACTIVISIONBLIZZARD_2016_10K', 'WALMART_2019_10K', 'AMD_2018_10K', 'AMD_2022_annualreport', 'AMD_2019_10K', 'AMD_2021_10K', 'WALMART_2020_10K', 'INTEL_2016_10K', 'WALMART_2017_10K', 'WALMART_2016_10K']
- `fb035` [direct] expected ['AMD_2022_10K'], top-20: ['AMD_2015_10K', 'AMD_2017_10K', 'AMD_2015_10K', 'AMD_2015_10K', 'AMD_2022_annualreport', 'AMD_2020_10K', 'AMD_2017_10K', 'AMD_2021_10K', 'AMD_2021_10K', 'AMD_2018_10K', 'AMD_2015_10K', 'AMD_2021_10K', 'AMD_2015_10K', 'AMD_2018_10K', 'AMD_2020_10K', 'AMD_2021_10K', 'AMD_2019_10K', 'AMD_2018_10K', 'AMD_2019_10K', 'AMD_2018_10K']
- `fb053` [direct] expected ['BESTBUY_2024Q2_10Q'], top-20: ['ACTIVSIONBLIZZARD_2023Q2_10Q', 'JOHNSON_JOHNSON_2022_10K', 'AMD_2016_10K', 'GENERALMILLS_2023_10K', 'JOHNSON_JOHNSON_2021_10K', 'ACTIVISIONBLIZZARD_2020_10K', 'NETFLIX_2023Q2_10Q', 'GENERALMILLS_2022_10K', 'VERIZON_2022_10K', 'COCACOLA_2022_10K', 'ORACLE_2021_10K', 'MICROSOFT_2020_10K', 'ORACLE_2023_10K', 'BESTBUY_2015_10K', 'BESTBUY_2023_10K', 'JPMORGAN_2021Q3_10Q', 'PAYPAL_2023Q2_10Q', 'BESTBUY_2021_10K', 'ORACLE_2022_10K', 'BESTBUY_2023_10K']
- `fb056` [table] expected ['BLOCK_2016_10K'], top-20: ['CORNING_2023Q2_10Q', '3M_2017_10K', '3M_2015_10K', '3M_2018_10K', 'ORACLE_2017_10K', '3M_2020_10K', 'ORACLE_2018_10K', '3M_2019_10K', 'ADOBE_2020_10K', '3M_2021_10K', 'ORACLE_2016_10K', 'ORACLE_2021_10K', '3M_2023Q2_10Q', 'PFIZER_2020_10K', 'EBAY_2020_10K', 'ORACLE_2015_10K', '3M_2022_10K', 'ORACLE_2019_10K', 'NIKE_2018_10K', 'ORACLE_2020_10K']
- `fb058` [table] expected ['BLOCK_2020_10K'], top-20: ['BLOCK_2022_10K', 'AMAZON_2020_10K', 'FOOTLOCKER_2023_10K', 'ORACLE_2020_10K', 'AMAZON_2021_10K', 'NIKE_2021_10K', 'BLOCK_2022_10K', 'FOOTLOCKER_2023_annualreport', 'NIKE_2022_10K', 'BLOCK_2022_8K_dated-2022-01-28', 'ORACLE_2022_10K', 'BLOCK_2022_10K', 'AMAZON_2022_10K', 'ORACLE_2018_10K', 'AMAZON_2017_10K', 'JOHNSON_JOHNSON_2021_10K', 'EBAY_2022_10K', 'AMAZON_2015_10K', 'MICROSOFT_2020_10K', 'GENERALMILLS_2020_10K']
- `fb066` [direct] expected ['BOEING_2022_10K'], top-20: ['3M_2022_10K', 'APPLE_2022_10K', 'BOEING_2017_10K', 'MICROSOFT_2020_10K', 'MICROSOFT_2019_10K', 'MICROSOFT_2020_10K', 'JOHNSON_JOHNSON_2022_10K', 'MICROSOFT_2020_10K', 'MICROSOFT_2018_10K', 'MICROSOFT_2019_10K', 'BOEING_2018_10K', 'ADOBE_2018_10K', 'BOEING_2017_10K', 'COCACOLA_2021_10K', 'COCACOLA_2020_10K', 'NIKE_2015_10K', 'INTEL_2021_10K', 'MICROSOFT_2023_10K', 'ORACLE_2020_10K', 'MICROSOFT_2018_10K']
- `fb081` [table] expected ['GENERALMILLS_2020_10K'], top-20: ['3M_2018_10K', '3M_2017_10K', '3M_2020_10K', '3M_2015_10K', '3M_2019_10K', '3M_2022_10K', '3M_2021_10K', 'CORNING_2023Q2_10Q', '3M_2023Q2_10Q', 'ORACLE_2020_10K', 'ORACLE_2021_10K', 'ORACLE_2019_10K', 'ORACLE_2023_10K', 'ADOBE_2020_10K', 'CORNING_2021_10K', 'PFIZER_2020_10K', '3M_2016_10K', 'GENERALMILLS_2023_annualreport', 'ORACLE_2018_10K', '3M_2015_10K']
- `fb089` [direct] expected ['JOHNSON_JOHNSON_2023_8K_dated-2023-08-30'], top-20: ['JOHNSON_JOHNSON_2016_10K', 'JOHNSON_JOHNSON_2015_10K', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2021_10K', 'JOHNSON_JOHNSON_2016_10K', 'JOHNSON_JOHNSON_2019_10K', 'JOHNSON_JOHNSON_2016_10K', 'JOHNSON_JOHNSON_2017_10K', 'JOHNSON_JOHNSON_2015_10K', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2020_10K', 'PFIZER_2020_10K', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2021_10K', 'PFIZER_2021_10K', 'JOHNSON_JOHNSON_2015_10K', 'JOHNSON_JOHNSON_2020_10K', 'PFIZER_2022_10K', 'JOHNSON_JOHNSON_2017_10K']
- `fb098` [table] expected ['LOCKHEEDMARTIN_2020_10K'], top-20: ['LOCKHEEDMARTIN_2017_10K', 'LOCKHEEDMARTIN_2015_10K', 'LOCKHEEDMARTIN_2016_10K', 'FOOTLOCKER_2023_annualreport', 'FOOTLOCKER_2023_10K', '3M_2016_10K', 'NIKE_2017_10K', 'WALMART_2024Q1_10Q', 'WALMART_2021_10K', 'NIKE_2016_10K', 'WALMART_2023_annualreport', 'FOOTLOCKER_2022_10K', 'FOOTLOCKER_2023_annualreport', 'WALMART_2021_10K', 'LOCKHEEDMARTIN_2018_10K', 'LOCKHEEDMARTIN_2023Q1_10Q', 'FOOTLOCKER_2023_10K', 'LOCKHEEDMARTIN_2023Q2_10Q', 'NIKE_2019_10K', 'NIKE_2020_10K']
- `fb105` [direct] expected ['MGMRESORTS_2022Q4_EARNINGS'], top-20: ['MGMRESORTS_2017_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2022_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2020_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2019_10K', 'MGMRESORTS_2020_10K', 'MGMRESORTS_2017_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2020_10K', 'MGMRESORTS_2020_10K', 'MGMRESORTS_2019_10K', 'MGMRESORTS_2020_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2022_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2023Q2_10Q']
- `fb125` [direct] expected ['Pfizer_2023Q2_10Q'], top-20: ['PFIZER_2021_10K', 'PFIZER_2022_10K', 'PFIZER_2019_10K', 'PFIZER_2021_10K', 'PFIZER_2019_10K', 'PFIZER_2021_10K', 'PFIZER_2020_10K', 'PFIZER_2019_10K', 'PFIZER_2022_10K', 'PFIZER_2022_10K', 'PFIZER_2020_10K', 'PFIZER_2019_10K', 'PFIZER_2021_10K', 'PFIZER_2021_10K', 'PFIZER_2021_10K', 'PFIZER_2020_10K', 'PFIZER_2020_10K', 'PFIZER_2019_10K', 'PFIZER_2022_10K', 'PFIZER_2020_10K']
- `fb130` [direct] expected ['ULTABEAUTY_2023Q4_EARNINGS'], top-20: ['ULTABEAUTY_2023_10K', 'COSTCO_2020_10K', 'COSTCO_2018_10K', 'FOOTLOCKER_2023_10K', 'AMCOR_2023_10K', 'FOOTLOCKER_2023_annualreport', 'COSTCO_2016_10K', 'GENERALMILLS_2015_10K', 'AMCOR_2022_10K', 'BESTBUY_2023_10K', 'COSTCO_2015_10K', 'FOOTLOCKER_2022_10Q', 'WALMART_2024Q1_10Q', 'GENERALMILLS_2023_10K', 'BESTBUY_2017_10K', 'AMCOR_2022_10K', 'BESTBUY_2016_10K', 'COSTCO_2017_10K', 'GENERALMILLS_2022_10K', '3M_2021_10K']
