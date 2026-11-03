# OCR results and quality statistics

This page reports **numbers only**. No text of the digitized books is published here
(see "Rights and what is not published").

## What was digitized

Scanned printed Karakalpak books were re-recognized from page images (the built-in text
layer of the scans is unusable because it was produced by a Russian OCR model):

* the 7-volume explanatory dictionary *Қарақалпақ тилиниң түсиндирме сөзлиги*
  (2nd, expanded edition, Nukus, 2023), in a structured form (headwords, senses, examples,
  idioms, cross-references);
* the folklore collection *Қарақалпақ фольклоры* (573 pages), as plain text.

Pipeline: Google Colab (CPU) + Gemini API (free tier), one page per request, one JSON
file per page, resumable. Code: `ocr_dict.py`, `run_all.py`, `ocr_qa.py`, `build_volume.py`
and the notebook `Karakalpak_OCR.ipynb`. See `docs/OCR_PIPELINE.md`.

## Volume statistics

| Volume | Dictionary pages | Headword entries | Rows | Word tokens | Distinct spellings |
|---|---|---|---|---|---|
| 1 | 380 (pp. 20-399) | 2,889 | 4,463 | 86,882 | 25,516 |
| 2 | 398 pages | ~2,770 | | | |
| 3 | 396 (pp. 4-399) | 4,156 | 6,306 | 102,135 | 28,720 |
| 4 | 396 (pp. 4-399) | 4,215 | 6,352 | 105,972 | 28,621 |
| 7 | 505 pages | ~6,500 | | ~114,000 | ~34,000 |

Volumes 5 and 6 are in progress. Folklore: 573 pages (554 with text, 13 only images),
about 149,000 words (about 36,000 distinct). "~" marks approximate figures.
"Distinct spellings" counts different written forms, not lemmas.

## Accuracy (random sample, manual check)

Each sample: 15 random pages, 10 words per page checked by eye against the page image
(150 words). Intervals are 95% Wilson intervals. Pages marked "redo" are not counted as
usable.

| Book | Wrong words | Error rate | 95% interval | Stage |
|---|---|---|---|---|
| Vol. 1 | 23 / 150 | 15.3% | 10.4-22.0% | raw OCR, before cleaning (includes one garbage page, since re-OCRed) |
| Vol. 2 | 5 / 150 | 3.3% | 1.4-7.6% | as recorded |
| Vol. 5 | 10 / 150 | 6.7% | 3.7-11.8% | raw OCR, before cleaning |
| Vol. 7 | 6 / 150 | 4.0% | 1.8-8.5% | as recorded |
| Folklore | 10 / 150 | 6.7% | 3.7-11.8% | raw OCR, before cleaning |

Pages flagged as suspicious by the automatic report are **not** a quality measure; only
the random sample is. Volumes 3, 4 and 6 have not been sampled yet.

## Main error types

* Letters with diacritics are replaced by look-alikes (e.g. ғ→р, қ→к, ң→н, ү→у).
* Latin letters inside Cyrillic words (e.g. Latin "e", "p", "ə" for Cyrillic "е", "п", "ә").
* On a few pages whole definitions are written in Latin letters instead of Cyrillic.
  These are fixed only by re-recognizing the page.
* Occasionally an empty result, or a lost continuation of a long entry.

Letter-level counts of automatic corrections are in `ocr_letter_confusions.csv`
(volumes 1, 3, 4; letters only, no words).

## Cleaning rules

1. OCR copies letters as printed; nothing is normalized inside the OCR step.
2. Normalization is a separate step with explicit rules, a change log, and the raw text kept.
3. Latin letters inside Cyrillic words are fixed by transliteration (heuristic, logged).
   Genuine Latin (for example etymology in parentheses) is left untouched.
4. A rare spelling is replaced only if the variant with ғ/қ/ң/ү/ў/ә/ө/ҳ is much more
   frequent in the same text.
5. The standard grammatical formula in verb entries is normalized by template.
6. Unicode is normalized to NFC; stray symbols such as ɵ are mapped to ө.
7. After a re-run, the best version of each page is chosen (less Latin and odd letters,
   without losing entries).

## Limitations

* Samples are small (150 words per book), so intervals are wide.
* The sampled words are mostly words with special letters, which are the hardest ones.
* Automatic checks cannot see a lost piece inside a page.
* The model can "correct" what is printed.
* Free-tier model names and limits can change.

## Rights and what is not published

The dictionary and the folklore collection are modern copyrighted editions. The full text,
tables of entries and page images are **not** published. Only code, method and statistics
are public. A request for permission to the publishing institute is planned.
