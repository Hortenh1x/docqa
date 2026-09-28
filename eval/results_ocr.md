# OCR evaluation (Tesseract, English, synthetic scans of the demo corpus)

19 typeset pages × 3 degradations; see `eval/ocr/run_ocr_eval.py` for how they are made.

| Variant | Pages | Word error rate (mean / median) | Heading recall | Mean confidence | s / page |
|---|---|---|---|---|---|
| scan | 19 | 0.002 / 0.000 | 0.99 | 95.2 | 3.3 |
| skewed | 19 | 0.083 / 0.000 | 0.83 | 92.1 | 7.8 |
| photo | 19 | 0.004 / 0.000 | 0.98 | 95.2 | 4.5 |

Word error rate = word-level edit distance between the typeset words and the recognised text, divided by the typeset word count (punctuation and case ignored). Heading recall = typeset headings that the line-height heuristic turned into section headings.
