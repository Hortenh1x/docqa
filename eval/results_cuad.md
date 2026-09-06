# Evaluation results — CUAD (real commercial contracts)

_Corpus: 509 contracts (CC-BY-4.0, Atticus Project) · embeddings text-embedding-3-small@1024 · rerank: none · LLM deepseek-v4-flash · judge deepseek-chat_

Golden set: `eval/golden_cuad.yaml` — 130 questions generated from the expert clause
annotations across 10 categories. Each question names the agreement and a party, so
retrieval must first find the right contract among 509. No `no_answer` questions here
either.

Reproduce:
`python -m eval.run_eval --collection <contracts-cuad id> --golden eval/golden_cuad.yaml --results eval/results_cuad.md --with-answers --judge --judge-model deepseek-chat --direct --concurrency 4`

## Retrieval quality by category

| Category | Questions | Recall@20 | Mean gate score |
| --- | --- | --- | --- |
| direct | 130 | 0.98 | 0.664 |
| **all answerable** | 130 | **0.98** | |

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
| 0.56 | 0.00 | 0.96 | 0.48 ← |
| 0.58 | 0.00 | 0.92 | 0.46 |
| 0.60 | 0.00 | 0.89 | 0.45 |
| 0.62 | 0.00 | 0.82 | 0.41 |
| 0.64 | 0.00 | 0.65 | 0.32 |
| 0.66 | 0.00 | 0.54 | 0.27 |
| 0.68 | 0.00 | 0.38 | 0.19 |
| 0.70 | 0.00 | 0.29 | 0.15 |

**Recommended `REFUSAL_THRESHOLD`: 0.56** — refuses 0% of off-corpus questions for $0 while passing 96% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 0/0
- False refusals on answerable questions: 43/130
- Citation precision (cited docs ∩ expected docs): 128/130

## LLM-judged answer quality (judge: deepseek-chat)

- Faithfulness (every claim supported by the excerpts): 84/87
- Correctness vs the golden expected answer: 78/87

## Reading the numbers

| Metric | Before widening | After widening |
| --- | --- | --- |
| Recall (expected contract among the retrieved chunks' documents) | 0.87 @8 | **0.98 @20** |
| Citation precision (cited document ∈ expected) | 109/125 (87%) | **128/130 (98%)** |
| Faithfulness — every claim backed by the excerpts (LLM-judged) | 67/68 (99%) | 84/87 (97%) |
| Correctness vs the expert annotation (LLM-judged) | 61/68 (90%) | 78/87 (90%) |
| Gave up instead of answering | 57/125 (46%) | **43/130 (33%)** |

Finding the right contract among 509 is now near-perfect (0.98). The remaining third of
refusals is the same chunk-level problem as on the filings: contracts are long and
repetitive, and a governing-law or anti-assignment clause is one paragraph among
hundreds — twenty chunks do not always catch it.

Note on the golden set: answers are the expert-annotated spans, so a correct paraphrase
is judged against raw contract language. The judge tolerates paraphrase, but the
correctness figure is conservative by construction.

This collection also exposed a scale bug: with one HNSW index spanning ~295k chunks,
pgvector applied the per-collection filter *after* the index scan, so some questions
against this 509-document collection returned **zero** vector hits and were refused for
free. Fixed by enabling iterative index scanning (`hnsw.iterative_scan`); every number
above is measured after that fix.

## Misses

- `cu018` [direct] expected ['BANGIINC_05_25_2005-EX-10-Premium_Managed_Hosting_Agreement'], top-20: ['BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'FOUNDATIONMEDICINE,INC_02_02_2015-EX-10.2-Collaboration_Agreement', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'OMINTO,INC_03_29_2004-EX-10-RESELLER_AGREEMENT', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement', 'VITAMINSHOPPECOMINC_09_13_1999-EX-10.26-SPONSORSHIP_AGREEMENT', 'CoherusBiosciencesInc_20200227_10-K_EX-10.29_12021376_EX-10.29_Development_Agreement', 'MTITECHNOLOGYCORP_11_16_2004-EX-10.102-Reseller_Agreement_Premier_Addendum', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'HEMISPHERX_-_Sales,_Marketing,_Distribution,_and_Supply_Agreement', 'GarrettMotionInc_20181001_8-K_EX-2.4_11364532_EX-2.4_Intellectual_Property_Agreement', 'BOLIVARMININGCORP_05_23_2003-EX-2.1-VISP_WEB_SITE_BUILDING_AND_HOSTING_AGREEMENT', 'QuantumGroupIncFl_20090120_8-K_EX-99.2_3672910_EX-99.2_Hosting_Agreement', 'VERTICALNETINC_04_01_2002-EX-10.19-MAINTENANCE_AND_SUPPORT_AGREEMENT', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'MusclepharmCorp_20170208_10-KA_EX-10.38_9893581_EX-10.38_Co-Branding_Agreement']
- `cu036` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-20: ['RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement', 'GarrettMotionInc_20181001_8-K_EX-2.4_11364532_EX-2.4_Intellectual_Property_Agreement', 'CerenceInc_20191002_8-K_EX-10.4_11827494_EX-10.4_Intellectual_Property_Agreement', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT', 'SigaTechnologiesInc_20190603_8-K_EX-10.1_11695818_EX-10.1_Promotion_Agreement', 'STARTECGLOBALCOMMUNICATIONSCORP_11_16_1998-EX-10.30-CONSTRUCTION_AND_MAINTENANCE_AGREEMENT', 'InmodeLtd_20190729_F-1A_EX-10.9_11743243_EX-10.9_Manufacturing_Agreement', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement', 'SoupmanInc_20150814_8-K_EX-10.1_9230148_EX-10.1_Franchise_Agreement1', 'ScansourceInc_20190822_10-K_EX-10.38_11793958_EX-10.38_Distributor_Agreement1', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT', 'ENTRUSTINC_07_24_1998-EX-10.5-STRATEGIC_ALLIANCE_AGREEMENT', 'Loop_Industries,_Inc._-_Marketing_Agreement', 'ScansourceInc_20190822_10-K_EX-10.38_11793958_EX-10.38_Distributor_Agreement1', 'RemarkHoldingsInc_20081114_10-Q_EX-10.24_2895649_EX-10.24_Content_License_Agreement', 'HfEnterprisesInc_20191223_S-1_EX-10.22_11931299_EX-10.22_Development_Agreement', 'RandWorldwideInc_20010402_8-KA_EX-10.2_2102464_EX-10.2_Co-Branding_Agreement', 'TELEGLOBEINTERNATIONALHOLDINGSLTD_03_29_2004-EX-10.10-CONSTRUCTION_AND_MAINTENANCE_AGREEMENT', 'IdeanomicsInc_20160330_10-K_EX-10.26_9512211_EX-10.26_Content_License_Agreement', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT']
