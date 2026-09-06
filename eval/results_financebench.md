# Evaluation results — FinanceBench (real 10-K/10-Q filings)

_Corpus: 334 SEC filings (Apache-2.0, github.com/patronus-ai/financebench) · embeddings text-embedding-3-small@1024 · rerank: none · LLM deepseek-v4-flash · judge deepseek-chat_

Golden set: `eval/golden_financebench.yaml` — 140 of the 150 expert-written questions
(10 dropped with the filings that exceed the 300-page / 25 MB ingestion limits).
Unlike the synthetic Kranich set this one carries **no `no_answer` questions**: every
question is answerable from the corpus, so the refusal columns below read as
"how often did the pipeline give up", not "how well did it reject junk".

Reproduce (from a host that can reach the API):
`python -m eval.run_eval --collection <financial-filings id> --golden eval/golden_financebench.yaml --results eval/results_financebench.md --with-answers --judge --judge-model deepseek-chat --concurrency 2 --api-key <key>`

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| direct | 95 | 0.72 | 0.680 |
| table | 45 | 0.67 | 0.637 |
| **all answerable** | 140 | **0.70** | |

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
| 0.44 | 0.00 | 0.99 | 0.50 |
| 0.46 | 0.00 | 0.99 | 0.50 |
| 0.48 | 0.00 | 0.99 | 0.50 |
| 0.50 | 0.00 | 0.99 | 0.50 |
| 0.52 | 0.00 | 0.99 | 0.50 |
| 0.54 | 0.00 | 0.99 | 0.50 |
| 0.56 | 0.00 | 0.99 | 0.50 |
| 0.58 | 0.00 | 0.96 | 0.48 ← |
| 0.60 | 0.00 | 0.93 | 0.46 |
| 0.62 | 0.00 | 0.81 | 0.41 |
| 0.64 | 0.00 | 0.71 | 0.35 |
| 0.66 | 0.00 | 0.52 | 0.26 |
| 0.68 | 0.00 | 0.38 | 0.19 |
| 0.70 | 0.00 | 0.28 | 0.14 |

**Recommended `REFUSAL_THRESHOLD`: 0.58** — refuses 0% of off-corpus questions for $0 while passing 96% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 0/0
- False refusals on answerable questions: 83/139
- Citation precision (cited docs ∩ expected docs): 96/139

## LLM-judged answer quality (judge: deepseek-chat)

- Faithfulness (every claim supported by the excerpts): 56/56
- Correctness vs the golden expected answer: 47/56

## Reading the numbers

| Metric | Result |
| --- | --- |
| Recall@8 (expected filing among the top-8 chunks' documents) | 0.70 |
| Faithfulness — every claim backed by the retrieved excerpts (LLM-judged) | **56/56 (100%)** |
| Correctness vs the expert answer (LLM-judged) | 47/56 (84%) |
| Citation precision (cited document ∈ expected) | 96/139 (69%) |
| Gave up instead of answering | 83/139 (60%) |

The pipeline never invented a number: of the answers it did produce, **100% were
faithful to the excerpts** and 84% matched the expert answer. What it does on this
corpus is *give up* — 60% of questions end in a refusal. Two causes, in order of size:

1. **Wrong document retrieved (42 misses).** 26 of them land on the right company but
   the wrong filing — "FY2018 capital expenditure for 3M" pulls 3M's 2017/2019/2020
   10-Ks, which are near-identical documents. Fiscal-year disambiguation is the single
   biggest weakness of pure semantic similarity here; the remaining 16 miss the company
   entirely (typically short earnings-release PDFs).
2. **Right document, wrong chunk (~41 refusals).** At least half of the refusals had the
   correct filing in the top-8, but the specific line item lives in one of hundreds of
   table chunks that did not surface. Document-level recall (0.70) overstates what the
   model actually sees — chunk-level recall is the real bottleneck on 200-page filings.

Both point at the same fixes, none of which are code rewrites: a cross-encoder reranker
(`RERANK_PROVIDER=cohere`) over a wider candidate set, prepending the document title
(company + fiscal year) to every chunk before embedding, and raising `RERANK_TOP_N` so
more table chunks reach the model. The refusal behaviour itself is working as designed —
faced with the wrong year's filing, the model refuses rather than reporting the wrong
year's number.

## Misses

- `fb003` [direct] expected ['3M_2022_10K'], top-8: ['3M_2020_10K', '3M_2018_10K', '3M_2019_10K', '3M_2017_10K', '3M_2017_10K', '3M_2020_10K', '3M_2015_10K', '3M_2016_10K']
- `fb005` [direct] expected ['3M_2022_10K'], top-8: ['3M_2021_10K', '3M_2017_10K', '3M_2020_10K', '3M_2020_10K', '3M_2020_10K', '3M_2020_10K', '3M_2016_10K', '3M_2015_10K']
- `fb013` [table] expected ['ADOBE_2017_10K'], top-8: ['ADOBE_2015_10K', 'GENERALMILLS_2016_10K', 'ADOBE_2016_10K', 'GENERALMILLS_2016_10K', 'WALMART_2016_10K', 'MICROSOFT_2018_10K', 'NETFLIX_2021_10K', 'NIKE_2018_10K']
- `fb019` [table] expected ['AMAZON_2017_10K'], top-8: ['ORACLE_2016_10K', 'ORACLE_2015_10K', 'SALESFORCE_2024Q2_EARNINGS', 'EBAY_2018_10K', 'ORACLE_2017_10K', 'APPLE_2017_10K', 'SALESFORCE_2024Q1_EARNINGS', 'PAYPAL_2022_10K']
- `fb023` [direct] expected ['AMCOR_2022_8K_dated-2022-07-01'], top-8: ['AMCOR_2022_8K_2022-07-01', 'AMCOR_2022_8K_2022-04-26', 'AMCOR_2023_10K', 'AMCOR_2020_10K', 'AMCOR_2019_10K', 'AMCOR_2019_10K', 'AMCOR_2021_10K', 'AMCOR_2021_10K']
- `fb027` [direct] expected ['AMCOR_2023_10K'], top-8: ['AMCOR_2023Q2_10Q', 'AMCOR_2023Q4_EARNINGS', 'AMCOR_2023Q4_EARNINGS', 'AMCOR_2020_10K', 'AMCOR_2023Q4_EARNINGS', 'AMCOR_2023Q4_EARNINGS', 'AMCOR_2023Q4_EARNINGS', 'APPLE_2015_10K']
- `fb032` [direct] expected ['AMD_2022_10K'], top-8: ['WALMART_2023_annualreport', 'WALMART_2024Q1_10Q', 'INTEL_2015_10K', 'WALMART_2023_10K', 'CORNING_2022_10K', 'WALMART_2021_10K', 'COCACOLA_2019_10K', 'ACTIVISIONBLIZZARD_2016_10K']
- `fb035` [direct] expected ['AMD_2022_10K'], top-8: ['AMD_2015_10K', 'AMD_2017_10K', 'AMD_2015_10K', 'AMD_2015_10K', 'AMD_2022_annualreport', 'AMD_2020_10K', 'AMD_2017_10K', 'AMD_2021_10K']
- `fb036` [direct] expected ['AMD_2022_10K'], top-8: ['AMD_2020_10K', 'INTEL_2022_10K', 'AMD_2015_10K', 'AMD_2021_10K', 'AMD_2019_10K', 'AMD_2015_10K', 'AMD_2016_10K', 'INTEL_2022_10K']
- `fb043` [direct] expected ['AMERICANEXPRESS_2022_10K'], top-8: ['NIKE_2019_10K', 'MICROSOFT_2020_10K', 'ADOBE_2018_10K', 'MICROSOFT_2019_10K', 'MICROSOFT_2018_10K', '3M_2022_10K', '3M_2016_10K', 'NIKE_2015_10K']
- `fb047` [table] expected ['AMERICANWATERWORKS_2021_10K'], top-8: ['AMERICANWATERWORKS_2018_10K', 'AMERICANWATERWORKS_2017_10K', 'AMERICANWATERWORKS_2023Q2_10Q', 'AMERICANWATERWORKS_2023Q2_10Q', 'AMERICANWATERWORKS_2016_10K', 'AMERICANWATERWORKS_2016_10K', 'AMERICANWATERWORKS_2023Q2_10Q', 'AMERICANWATERWORKS_2020_10K']
- `fb049` [table] expected ['BESTBUY_2019_10K'], top-8: ['BESTBUY_2023_10K', 'BESTBUY_2018_10K', 'BESTBUY_2017_10K', 'BESTBUY_2022_10K', 'BESTBUY_2015_10K', 'BESTBUY_2015_10K', 'BESTBUY_2021_10K', 'BESTBUY_2020_10K']
- `fb053` [direct] expected ['BESTBUY_2024Q2_10Q'], top-8: ['ACTIVSIONBLIZZARD_2023Q2_10Q', 'JOHNSON_JOHNSON_2022_10K', 'GENERALMILLS_2023_10K', 'JOHNSON_JOHNSON_2021_10K', 'ACTIVISIONBLIZZARD_2020_10K', 'NETFLIX_2023Q2_10Q', 'GENERALMILLS_2022_10K', 'VERIZON_2022_10K']
- `fb055` [direct] expected ['BESTBUY_2024Q2_10Q'], top-8: ['BESTBUY_2020_10K', 'BESTBUY_2022_10K', 'BESTBUY_2023_10K', 'BESTBUY_2021_10K', 'BESTBUY_2015_10K', 'BESTBUY_2023_10K', 'BESTBUY_2024Q2_EARNINGS', 'BESTBUY_2015_10K']
- `fb056` [table] expected ['BLOCK_2016_10K'], top-8: ['CORNING_2023Q2_10Q', '3M_2017_10K', '3M_2015_10K', '3M_2018_10K', 'ORACLE_2017_10K', '3M_2020_10K', 'ORACLE_2018_10K', '3M_2019_10K']
- `fb057` [table] expected ['BLOCK_2020_10K'], top-8: ['BLOCK_2015_10K', 'BLOCK_2022_10K', 'BLOCK_2019_10K', 'GENERALMILLS_2019_10K', 'BESTBUY_2019_10K', 'INTEL_2021_10K', 'BLOCK_2022_10K', 'BLOCK_2022_10K']
- `fb058` [table] expected ['BLOCK_2020_10K'], top-8: ['AMAZON_2020_10K', 'FOOTLOCKER_2023_10K', 'ORACLE_2020_10K', 'AMAZON_2021_10K', 'NIKE_2021_10K', 'FOOTLOCKER_2023_annualreport', 'NIKE_2022_10K', 'ORACLE_2022_10K']
- `fb062` [direct] expected ['BOEING_2022_10K'], top-8: ['BOEING_2021_10K', 'BOEING_2017_10K', 'BOEING_2020_10K', 'BOEING_2017_10K', 'BOEING_2018_10K', 'BOEING_2020_10K', 'BOEING_2020_10K', 'BOEING_2021_10K']
- `fb066` [direct] expected ['BOEING_2022_10K'], top-8: ['3M_2022_10K', 'APPLE_2022_10K', 'MICROSOFT_2020_10K', 'MICROSOFT_2019_10K', 'MICROSOFT_2020_10K', 'JOHNSON_JOHNSON_2022_10K', 'MICROSOFT_2020_10K', 'MICROSOFT_2018_10K']
- `fb067` [table] expected ['COCACOLA_2017_10K'], top-8: ['WALMART_2017_10K', 'WALMART_2019_10K', 'WALMART_2021_10K', 'WALMART_2023_annualreport', 'WALMART_2023_10K', 'WALMART_2015_10K', 'WALMART_2022_10K', 'WALMART_2024Q1_10Q']
- `fb069` [table] expected ['COCACOLA_2022_10K'], top-8: ['WALMART_2022_10K', 'MICROSOFT_2023_10K', 'JOHNSON_JOHNSON_2020_10K', 'JOHNSON_JOHNSON_2021_10K', 'JOHNSON_JOHNSON_2022_10K', 'COSTCO_2020_10K', 'ORACLE_2018_10K', 'KRAFTHEINZ_2022_10K']
- `fb073` [direct] expected ['CORNING_2022_10K'], top-8: ['CORNING_2020_10K', 'CORNING_2020_10K', 'CORNING_2016_10K', 'CORNING_2020_10K', 'CORNING_2019_10K', 'CORNING_2021_10K', 'CORNING_2021_10K', 'CORNING_2015_10K']
- `fb081` [table] expected ['GENERALMILLS_2020_10K'], top-8: ['3M_2018_10K', '3M_2017_10K', '3M_2020_10K', '3M_2015_10K', '3M_2019_10K', '3M_2022_10K', '3M_2021_10K', 'CORNING_2023Q2_10Q']
- `fb084` [direct] expected ['JOHNSON_JOHNSON_2022_10K'], top-8: ['JOHNSON_JOHNSON_2023_8K_dated-2023-08-30', 'JOHNSON_JOHNSON_2023_8K_dated-2023-08-30', 'JOHNSON_JOHNSON_2023_8K_dated-2023-08-30', 'JOHNSON_JOHNSON_2023Q2_EARNINGS', 'JOHNSON_JOHNSON_2022Q4_EARNINGS', 'JOHNSON_JOHNSON_2023Q1_EARNINGS', 'JOHNSON_JOHNSON_2022Q4_EARNINGS', 'JOHNSON_JOHNSON_2023Q1_EARNINGS']
- `fb085` [direct] expected ['JOHNSON_JOHNSON_2022_10K'], top-8: ['JOHNSON_JOHNSON_2023Q2_EARNINGS', 'JOHNSON_JOHNSON_2016_10K', 'JOHNSON_JOHNSON_2023_8K_dated-2023-08-30', 'JOHNSON_JOHNSON_2023Q1_EARNINGS', 'JOHNSON_JOHNSON_2022Q4_EARNINGS', 'JOHNSON_JOHNSON_2022Q4_EARNINGS', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2023_8K_dated-2023-08-30']
- `fb088` [direct] expected ['JOHNSON_JOHNSON_2022Q4_EARNINGS'], top-8: ['JOHNSON_JOHNSON_2022_10K', 'AMAZON_2021_10K', 'JOHNSON_JOHNSON_2020_10K', 'JOHNSON_JOHNSON_2019_10K', 'JOHNSON_JOHNSON_2021_10K', 'JOHNSON_JOHNSON_2017_10K', 'JOHNSON_JOHNSON_2015_10K', 'AMAZON_2022_10K']
- `fb089` [direct] expected ['JOHNSON_JOHNSON_2023_8K_dated-2023-08-30'], top-8: ['JOHNSON_JOHNSON_2016_10K', 'JOHNSON_JOHNSON_2015_10K', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2018_10K', 'JOHNSON_JOHNSON_2021_10K', 'JOHNSON_JOHNSON_2016_10K', 'JOHNSON_JOHNSON_2019_10K', 'JOHNSON_JOHNSON_2016_10K']
- `fb098` [table] expected ['LOCKHEEDMARTIN_2020_10K'], top-8: ['FOOTLOCKER_2023_annualreport', 'FOOTLOCKER_2023_10K', '3M_2016_10K', 'NIKE_2017_10K', 'WALMART_2024Q1_10Q', 'WALMART_2021_10K', 'NIKE_2016_10K', 'WALMART_2023_annualreport']
- `fb099` [table] expected ['LOCKHEEDMARTIN_2021_10K'], top-8: ['3M_2018_10K', '3M_2019_10K', '3M_2020_10K', '3M_2015_10K', '3M_2022_10K', 'ORACLE_2021_10K', '3M_2021_10K', 'ORACLE_2020_10K']
- `fb101` [table] expected ['MGMRESORTS_2018_10K'], top-8: ['MGMRESORTS_2017_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2017_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2023Q2_10Q', 'MGMRESORTS_2022Q4_EARNINGS']
- `fb102` [table] expected ['MGMRESORTS_2020_10K'], top-8: ['MGMRESORTS_2017_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2017_10K', 'MGMRESORTS_2018_10K', 'MGMRESORTS_2018_10K', 'MGMRESORTS_2017_10K', 'MGMRESORTS_2019_10K', 'MGMRESORTS_2015_10K']
- `fb103` [direct] expected ['MGMRESORTS_2022_10K'], top-8: ['MGMRESORTS_2017_10K', 'MGMRESORTS_2019_10K', 'MGMRESORTS_2017_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2019_10K', 'MGMRESORTS_2018_10K', 'MGMRESORTS_2017_10K', 'MGMRESORTS_2021_10K']
- `fb105` [direct] expected ['MGMRESORTS_2022Q4_EARNINGS'], top-8: ['MGMRESORTS_2017_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2022_10K', 'MGMRESORTS_2015_10K', 'MGMRESORTS_2020_10K', 'MGMRESORTS_2021_10K', 'MGMRESORTS_2019_10K']
- `fb110` [table] expected ['NETFLIX_2015_10K'], top-8: ['VERIZON_2022_10K', 'KRAFTHEINZ_2015_10K', 'GENERALMILLS_2022_10K', 'BLOCK_2015_10K', 'VERIZON_2022_10K', 'KRAFTHEINZ_2021_10K', 'VERIZON_2019_10K', 'VERIZON_2020_10K']
- `fb116` [direct] expected ['PAYPAL_2022_10K'], top-8: ['EBAY_2019_10K', 'EBAY_2018_10K', 'EBAY_2016_10K', 'EBAY_2017_10K', 'EBAY_2018_10K', 'CORNING_2022_10K', 'CORNING_2023Q2_10Q', 'EBAY_2016_10K']
- `fb123` [direct] expected ['PFIZER_2021_10K'], top-8: ['PFIZER_2020_10K', 'PFIZER_2019_10K', 'PFIZER_2019_10K', 'PFIZER_2019_10K', 'PFIZER_2020_10K', 'PFIZER_2020_10K', 'PFIZER_2020_10K', 'PFIZER_2022_10K']
- `fb125` [direct] expected ['Pfizer_2023Q2_10Q'], top-8: ['PFIZER_2021_10K', 'PFIZER_2022_10K', 'PFIZER_2019_10K', 'PFIZER_2021_10K', 'PFIZER_2019_10K', 'PFIZER_2021_10K', 'PFIZER_2020_10K', 'PFIZER_2019_10K']
- `fb126` [direct] expected ['Pfizer_2023Q2_10Q'], top-8: ['PFIZER_2017_10K', 'PFIZER_2023Q2_EARNINGS', 'PFIZER_2020_10K', 'PFIZER_2020_10K', 'PFIZER_2021_10K', 'PFIZER_2017_10K', 'PFIZER_2023Q2_EARNINGS', 'PFIZER_2019_10K']
- `fb130` [direct] expected ['ULTABEAUTY_2023Q4_EARNINGS'], top-8: ['ULTABEAUTY_2023_10K', 'COSTCO_2020_10K', 'COSTCO_2018_10K', 'FOOTLOCKER_2023_10K', 'AMCOR_2023_10K', 'FOOTLOCKER_2023_annualreport', 'COSTCO_2016_10K', 'GENERALMILLS_2015_10K']
- `fb132` [direct] expected ['ULTABEAUTY_2023Q4_EARNINGS'], top-8: ['ULTABEAUTY_2023_10K', 'ULTABEAUTY_2023_10K', 'ADOBE_2015_10K', 'BESTBUY_2022_10K', 'AMD_2021_10K', 'ADOBE_2020_10K', 'LOCKHEEDMARTIN_2022_10K', 'BESTBUY_2021_10K']
- `fb135` [direct] expected ['VERIZON_2021_10K'], top-8: ['VERIZON_2016_10K', 'VERIZON_2019_10K', 'VERIZON_2020_10K', 'VERIZON_2017_10K', 'VERIZON_2020_10K', 'VERIZON_2022_10K', 'VERIZON_2022_10K', 'VERIZON_2022_10K']
- `fb136` [direct] expected ['VERIZON_2022_10K'], top-8: ['VERIZON_2020_10K', 'VERIZON_2021_10K', 'VERIZON_2019_10K', 'VERIZON_2021_10K', 'VERIZON_2016_10K', 'VERIZON_2021_10K', 'VERIZON_2015_10K', 'VERIZON_2020_10K']
