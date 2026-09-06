# Evaluation results — CUAD (real commercial contracts)

_Corpus: 509 contracts (CC-BY-4.0, Atticus Project) · embeddings text-embedding-3-small@1024 · rerank: none · LLM deepseek-v4-flash · judge deepseek-chat_

Golden set: `eval/golden_cuad.yaml` — 130 questions generated from the expert clause
annotations across 10 categories (agreement date, governing law, parties, expiration,
renewal, non-compete, exclusivity, liability cap, minimum commitment, anti-assignment).
Each question names the agreement and a party, so retrieval must first find the right
contract among 509. No `no_answer` questions here either.

Reproduce:
`python -m eval.run_eval --collection <contracts-cuad id> --golden eval/golden_cuad.yaml --results eval/results_cuad.md --with-answers --judge --judge-model deepseek-chat --concurrency 2 --api-key <key>`

## Retrieval quality by category

| Category | Questions | Recall@8 | Mean gate score |
| --- | --- | --- | --- |
| direct | 130 | 0.87 | 0.655 |
| **all answerable** | 130 | **0.87** | |

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
| 0.42 | 0.00 | 0.99 | 0.50 |
| 0.44 | 0.00 | 0.99 | 0.50 |
| 0.46 | 0.00 | 0.99 | 0.50 |
| 0.48 | 0.00 | 0.98 | 0.49 |
| 0.50 | 0.00 | 0.98 | 0.49 |
| 0.52 | 0.00 | 0.98 | 0.49 |
| 0.54 | 0.00 | 0.97 | 0.48 ← |
| 0.56 | 0.00 | 0.90 | 0.45 |
| 0.58 | 0.00 | 0.85 | 0.42 |
| 0.60 | 0.00 | 0.82 | 0.41 |
| 0.62 | 0.00 | 0.75 | 0.38 |
| 0.64 | 0.00 | 0.62 | 0.31 |
| 0.66 | 0.00 | 0.52 | 0.26 |
| 0.68 | 0.00 | 0.38 | 0.19 |
| 0.70 | 0.00 | 0.28 | 0.14 |

**Recommended `REFUSAL_THRESHOLD`: 0.54** — refuses 0% of off-corpus questions for $0 while passing 97% of answerable ones. The retrieval gate is deliberately conservative: off-corpus questions that slip through are still converted to refusals by the NO_ANSWER generation gate (at the cost of one LLM call).

## Answer layer (full pipeline)

- End-to-end refusal rate on no_answer: 0/0
- False refusals on answerable questions: 57/125
- Citation precision (cited docs ∩ expected docs): 109/125

## LLM-judged answer quality (judge: deepseek-chat)

- Faithfulness (every claim supported by the excerpts): 67/68
- Correctness vs the golden expected answer: 61/68

## Reading the numbers

| Metric | Result |
| --- | --- |
| Recall@8 (expected contract among the top-8 chunks' documents) | 0.87 |
| Faithfulness — every claim backed by the retrieved excerpts (LLM-judged) | **67/68 (99%)** |
| Correctness vs the expert annotation (LLM-judged) | 61/68 (90%) |
| Citation precision (cited document ∈ expected) | 109/125 (87%) |
| Gave up instead of answering | 57/125 (46%) |

Finding the right contract among 509 works well (0.87). The refusals are dominated by
the **right document, wrong chunk** pattern: only 17 questions missed the document, yet
57 ended in a refusal — so ~40 refusals had the correct contract retrieved and still
lacked the clause. Contracts are long and repetitive, and a governing-law or
anti-assignment clause is one paragraph among hundreds; eight chunks are not always
enough to catch it.

Note on the golden set: answers are the expert-annotated spans, so a correct paraphrase
("California law governs") is judged against the raw span ("This Agreement shall be
governed by the laws of the State of California…"). The judge tolerates paraphrase, but
the correctness figure is conservative by construction.

This collection is also what exposed a scale bug: with one HNSW index spanning ~295k
chunks, pgvector applied the per-collection filter *after* the index scan, so questions
against this 509-document collection sometimes returned **zero** vector hits and were
refused for free. Fixed by enabling iterative index scanning (`hnsw.iterative_scan`);
every number above is measured after that fix.

## Misses

- `cu008` [direct] expected ['AURASYSTEMSINC_06_16_2010-EX-10.25-STRATEGIC_ALLIANCE_AGREEMENT'], top-8: ['PhotronicsInc_20171219_10-QA_EX-10.28_10982650_EX-10.28_Outsourcing_Agreement', 'BloomEnergyCorp_20180321_DRSA_(on_S-1)_EX-10_11240356_EX-10_Maintenance_Agreement', 'IMMUNOMEDICSINC_08_07_2019-EX-10.1-PROMOTION_AGREEMENT', 'AudibleInc_20001113_10-Q_EX-10.32_2599586_EX-10.32_Co-Branding_Agreement__Marketing_Agreement__Investment_Distribution_Agreement', 'TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT_VENTURE_AGREEMENT', 'EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding_Agreement', 'FreezeTagInc_20180411_8-K_EX-10.1_11139603_EX-10.1_Sponsorship_Agreement', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement']
- `cu014` [direct] expected ['BANGIINC_05_25_2005-EX-10-Premium_Managed_Hosting_Agreement'], top-8: ['VITAMINSHOPPECOMINC_09_13_1999-EX-10.26-SPONSORSHIP_AGREEMENT', 'VITAMINSHOPPECOMINC_09_13_1999-EX-10.26-SPONSORSHIP_AGREEMENT', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'VITAMINSHOPPECOMINC_09_13_1999-EX-10.26-SPONSORSHIP_AGREEMENT', 'AgapeAtpCorp_20191202_10-KA_EX-10.1_11911128_EX-10.1_Supply_Agreement', 'VITAMINSHOPPECOMINC_09_13_1999-EX-10.26-SPONSORSHIP_AGREEMENT', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'VITAMINSHOPPECOMINC_09_13_1999-EX-10.26-SPONSORSHIP_AGREEMENT']
- `cu018` [direct] expected ['BANGIINC_05_25_2005-EX-10-Premium_Managed_Hosting_Agreement'], top-8: ['BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'FOUNDATIONMEDICINE,INC_02_02_2015-EX-10.2-Collaboration_Agreement', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'OMINTO,INC_03_29_2004-EX-10-RESELLER_AGREEMENT', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement', 'BEYONDCOMCORP_08_03_2000-EX-10.2-CO-HOSTING_AGREEMENT', 'RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement']
- `cu023` [direct] expected ['PFSFUNDS_06_26_2020-EX-99.H_OTH_MAT_CONT-SERVICES_AGREEMENT'], top-8: ['ENERGOUSCORP_03_16_2017-EX-10.24-STRATEGIC_ALLIANCE_AGREEMENT', 'VIRTUALSCOPICS,INC_11_12_2010-EX-10.1-STRATEGIC_ALLIANCE_AGREEMENT', 'JOINTCORP_09_19_2014-EX-10.15-FRANCHISE_AGREEMENT', 'VIRTUALSCOPICS,INC_11_12_2010-EX-10.1-STRATEGIC_ALLIANCE_AGREEMENT', 'GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise_Agreement', 'VIRTUALSCOPICS,INC_11_12_2010-EX-10.1-STRATEGIC_ALLIANCE_AGREEMENT', 'CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING_AGREEMENT', 'MEDALISTDIVERSIFIEDREIT,INC_05_18_2020-EX-10.1-CONSULTING_AGREEMENT']
- `cu028` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-8: ['MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'OASYSMOBILE,INC_07_05_2001-EX-10.17-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT']
- `cu031` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-8: ['MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'PHREESIA,INC_05_28_2019-EX-10.18-STRATEGIC_ALLIANCE_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT']
- `cu032` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-8: ['CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING_AGREEMENT', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT', 'ElPolloLocoHoldingsInc_20200306_10-K_EX-10.16_12041700_EX-10.16_Development_Agreement', 'ENERGOUSCORP_03_16_2017-EX-10.24-STRATEGIC_ALLIANCE_AGREEMENT', 'GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise_Agreement', 'ConformisInc_20191101_10-Q_EX-10.6_11861402_EX-10.6_Development_Agreement', 'BUFFALOWILDWINGSINC_06_05_1998-EX-10.3-FRANCHISE_AGREEMENT', 'DRIVENDELIVERIES,INC_05_22_2020-EX-10.4-CONSULTING_AGREEMENT']
- `cu034` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-8: ['BloomEnergyCorp_20180321_DRSA_(on_S-1)_EX-10_11240356_EX-10_Maintenance_Agreement', 'IMMUNOMEDICSINC_08_07_2019-EX-10.1-PROMOTION_AGREEMENT', 'PhotronicsInc_20171219_10-QA_EX-10.28_10982650_EX-10.28_Outsourcing_Agreement', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT', 'EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding_Agreement', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement', 'EhaveInc_20190515_20-F_EX-4.44_11678816_EX-4.44_License_Agreement__Reseller_Agreement', 'VAPOTHERM,_INC._-_Manufacturing_and_Supply_Agreement']
- `cu035` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-8: ['MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'MANUFACTURERSSERVICESLTD_06_05_2000-EX-10.14-OUTSOURCING_AGREEMENT', 'GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise_Agreement']
- `cu036` [direct] expected ['DRAGONSYSTEMSINC_01_08_1999-EX-10.17-OUTSOURCING_AGREEMENT'], top-8: ['RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement', 'GarrettMotionInc_20181001_8-K_EX-2.4_11364532_EX-2.4_Intellectual_Property_Agreement', 'CerenceInc_20191002_8-K_EX-10.4_11827494_EX-10.4_Intellectual_Property_Agreement', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT', 'SigaTechnologiesInc_20190603_8-K_EX-10.1_11695818_EX-10.1_Promotion_Agreement', 'STARTECGLOBALCOMMUNICATIONSCORP_11_16_1998-EX-10.30-CONSTRUCTION_AND_MAINTENANCE_AGREEMENT', 'InmodeLtd_20190729_F-1A_EX-10.9_11743243_EX-10.9_Manufacturing_Agreement', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement']
- `cu043` [direct] expected ['VIRGINGALACTICHOLDINGS,INC_04_08_2020-EX-99.1-JOINT_FILING_STATEMENT'], top-8: ['RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement', 'RemarkHoldingsInc_20081114_10-Q_EX-10.24_2895649_EX-10.24_Content_License_Agreement', 'Loop_Industries,_Inc._-_Marketing_Agreement', 'AudibleInc_20001113_10-Q_EX-10.32_2599586_EX-10.32_Co-Branding_Agreement__Marketing_Agreement__Investment_Distribution_Agreement', 'ARMSTRONGFLOORING,INC_01_07_2019-EX-10.2-INTELLECTUAL_PROPERTY_AGREEMENT', 'Loop_Industries,_Inc._-_Marketing_Agreement', 'GarrettMotionInc_20181001_8-K_EX-2.4_11364532_EX-2.4_Intellectual_Property_Agreement', 'BUFFALOWILDWINGSINC_06_05_1998-EX-10.3-FRANCHISE_AGREEMENT']
- `cu076` [direct] expected ['MusclepharmCorp_20170208_10-KA_EX-10.38_9893581_EX-10.38_Co-Branding_Agreement'], top-8: ['MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise_Agreement', 'ElPolloLocoHoldingsInc_20200306_10-K_EX-10.16_12041700_EX-10.16_Development_Agreement', 'MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise_Agreement', 'PalmerSquareCapitalBdcInc_20200116_10-12GA_EX-10.6_11949289_EX-10.6_Trademark_License_Agreement']
- `cu080` [direct] expected ['MusclepharmCorp_20170208_10-KA_EX-10.38_9893581_EX-10.38_Co-Branding_Agreement'], top-8: ['MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'ARMSTRONGFLOORING,INC_01_07_2019-EX-10.2-INTELLECTUAL_PROPERTY_AGREEMENT', 'MorganStanleyDirectLendingFund_20191119_10-12GA_EX-10.5_11898508_EX-10.5_Trademark_License_Agreement', 'RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement', 'GarrettMotionInc_20181001_8-K_EX-2.4_11364532_EX-2.4_Intellectual_Property_Agreement', 'IdeanomicsInc_20160330_10-K_EX-10.26_9512211_EX-10.26_Content_License_Agreement', 'CerenceInc_20191002_8-K_EX-10.4_11827494_EX-10.4_Intellectual_Property_Agreement']
- `cu092` [direct] expected ['BLUEROCKRESIDENTIALGROWTHREIT,INC_06_01_2016-EX-1.1-AGENCY_AGREEMENT'], top-8: ['MEDALISTDIVERSIFIEDREIT,INC_05_18_2020-EX-10.1-CONSULTING_AGREEMENT', 'MEDALISTDIVERSIFIEDREIT,INC_05_18_2020-EX-10.1-CONSULTING_AGREEMENT', 'JOINTCORP_09_19_2014-EX-10.15-FRANCHISE_AGREEMENT', 'MEDALISTDIVERSIFIEDREIT,INC_05_18_2020-EX-10.1-CONSULTING_AGREEMENT', 'SUCAMPOPHARMACEUTICALS,INC_11_04_2015-EX-10.2-STRATEGIC_ALLIANCE_AGREEMENT', 'MEDALISTDIVERSIFIEDREIT,INC_05_18_2020-EX-10.1-CONSULTING_AGREEMENT', 'GOOSEHEADINSURANCE,INC_04_02_2018-EX-10.6-Franchise_Agreement', 'CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING_AGREEMENT']
- `cu096` [direct] expected ['BLUEROCKRESIDENTIALGROWTHREIT,INC_06_01_2016-EX-1.1-AGENCY_AGREEMENT'], top-8: ['RangeResourcesLouisianaInc_20150417_8-K_EX-10.5_9045501_EX-10.5_Transportation_Agreement', 'Loop_Industries,_Inc._-_Marketing_Agreement', 'GarrettMotionInc_20181001_8-K_EX-2.4_11364532_EX-2.4_Intellectual_Property_Agreement', 'CerenceInc_20191002_8-K_EX-10.4_11827494_EX-10.4_Intellectual_Property_Agreement', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT', 'RemarkHoldingsInc_20081114_10-Q_EX-10.24_2895649_EX-10.24_Content_License_Agreement', 'TELEGLOBEINTERNATIONALHOLDINGSLTD_03_29_2004-EX-10.10-CONSTRUCTION_AND_MAINTENANCE_AGREEMENT', 'BERKELEYLIGHTS,INC_06_26_2020-EX-10.12-COLLABORATION_AGREEMENT']
- `cu111` [direct] expected ['ZEBRATECHNOLOGIESCORP_04_16_2014-EX-10.1-INTELLECTUAL_PROPERTY_AGREEMENT'], top-8: ['InmodeLtd_20190729_F-1A_EX-10.9_11743243_EX-10.9_Manufacturing_Agreement', 'ENERGOUSCORP_03_16_2017-EX-10.24-STRATEGIC_ALLIANCE_AGREEMENT', 'PhotronicsInc_20171219_10-QA_EX-10.28_10982650_EX-10.28_Outsourcing_Agreement', 'UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing_Agreement__Supply_Agreement', 'RandWorldwideInc_20010402_8-KA_EX-10.2_2102464_EX-10.2_Co-Branding_Agreement', 'SFGFINANCIALCORP_05_12_2009-EX-10.1-SOFTWARE_LICENSE_AND_MAINTENANCE_AGREEMENT', 'IMMUNOMEDICSINC_08_07_2019-EX-10.1-PROMOTION_AGREEMENT', 'InmodeLtd_20190729_F-1A_EX-10.9_11743243_EX-10.9_Manufacturing_Agreement']
- `cu128` [direct] expected ['HYDRONTECHNOLOGIESINC_03_31_1997-EX-10.47-SPONSORSHIP_AGREEMENT'], top-8: ['CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING_AGREEMENT', 'KUBIENT,INC_07_02_2020-EX-10.14-MASTER_SERVICES_AGREEMENT_Part2', 'AIRTECHINTERNATIONALGROUPINC_05_08_2000-EX-10.4-FRANCHISE_AGREEMENT', 'JOINTCORP_09_19_2014-EX-10.15-FRANCHISE_AGREEMENT', 'ENERGOUSCORP_03_16_2017-EX-10.24-STRATEGIC_ALLIANCE_AGREEMENT', 'Quaker_Chemical_Corporation_-_NON_COMPETITION_AND_NON_SOLICITATION_AGREEMENT', 'Quaker_Chemical_Corporation_-_NON_COMPETITION_AND_NON_SOLICITATION_AGREEMENT', 'Quaker_Chemical_Corporation_-_NON_COMPETITION_AND_NON_SOLICITATION_AGREEMENT']
