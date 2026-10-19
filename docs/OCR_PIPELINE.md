# OCR pipeline for printed Karakalpak

Notes on how scanned Karakalpak books were digitised, what went wrong, and what was changed. Written to be reproducible and to be honest about quality.

## 1. Problem

The source PDFs are scans of printed books in Karakalpak Cyrillic. They already contain an invisible text layer made by commercial OCR software, but the engine was set to Russian. Karakalpak-specific letters were replaced by look-alikes:

| Printed | Layer shows |
|---|---|
| ә | э |
| ғ | р |
| қ | к |
| ң | н |
| ө | о / 0 |
| ү, ў | у |

The result looks almost right, but words no longer match any lexicon, so the layer cannot be used. Re-reading the page images is necessary.

## 2. Approach

Vision language model, **one page image per request**, with a fixed JSON schema (dictionary mode) or plain text (text mode, for folklore, prose and verse).

Dictionary schema per page: printed page number; entries with headword, label (part of speech or reference), numbered senses with optional field label, examples with source, idioms with definitions and examples, cross-reference, flags for entries that continue across pages and for uncertain readings.

Engineering details:

- each page is saved to its own file; finished pages are skipped, so runs are resumable;
- retry with back-off on server overload, stop cleanly on a daily quota;
- the log records tokens per page and a completeness check against the structure of the (letter-garbled) PDF text layer: if the model returns clearly fewer headwords than the layer shows, the page is flagged;
- request temperature 0.

## 3. What went wrong (and how it was handled)

| Problem | How it appeared | Handling |
|---|---|---|
| Skipped pages in a whole-file request | a chat session processed pages 99, 102-103 and silently skipped two in between | one page per request, page number set by the script, not the model |
| Special letters misread | ғ→р, қ→к, ң→н (for example a headword read as ТӘРРИП instead of ТӘҒРИП) | conservative automatic correction: a rare spelling is replaced only if a variant with the special letter is far more frequent in the same text and in a reference word list; every change is logged |
| Idioms dropped | bold phrases inside entries were lost in the first prompt | explicit field for phraseological units in the schema and prompt |
| Page number copied from the prompt | the model reused the example number from the instructions | page number now comes from the script |
| Latin letters inside Cyrillic words | words such as "болmasa"; occasionally whole definitions transliterated | detection by script mixing; affected pages re-run with an explicit Cyrillic-only rule; the better of two versions is kept per page (fewer Latin fragments, no lost entries); the rest are listed for review |
| Stray combining marks | a breve as a separate character after a letter | Unicode NFC normalisation |
| Formulaic definitions corrupted | the stock phrase "(verb) фейилиниң өзгелик дәрежеси" (causative of a verb) appears in hundreds of entries and was written in many variants | all variants within a small edit distance normalised to the canonical form; the first word is checked against the headword list |
| Entries silently lost | one page returned 4 entries in the first run and 15 in the re-run | comparing two runs on the same page exposes this; it cannot be detected everywhere, which is why a manual sample is needed |
| Auto-correction by the model | the model "repaired" a plain printed letter to the expected special one | correction is treated as noise, not as transcription; the output is not diplomatic |

## 4. Cost and time

On a free API tier, with a lightweight model: about 1,600 input and 1,900 output tokens per page; roughly 500 pages per day; about one 500-page volume per day. Prices and limits change, check the provider's current terms.

## 5. Evaluation

Automatic checks (counts of Latin fragments, headword counts against the text layer, rare-spelling lists) only find some errors. Planned: a manual comparison on 15 random pages, about 150 words, counting words with wrong special letters, lost entries and merged or split entries, and reporting the share of incorrect words with the sampling procedure. Results will be added to the README.

## 6. Known limitations

- Rare words with wrong special letters are invisible to the frequency-based check.
- Entries lost inside a page are not always detected.
- Headword checks depend on the reference word list, which is built from three epic texts and does not cover the whole vocabulary of a general dictionary.
- Output is machine-read text, not a verified edition.

## 7. Rights

The scans come from printed publications. Raw scans and full extracted text of copyrighted works are not published in this repository.


## 8. Plain-text mode and the folklore edition: additional lessons

- **Do not assume the orthography.** I first assumed that the letters ұ and һ do not belong to Karakalpak and nearly told the model never to output them. The folklore edition does print ұ (and rarely һ), so the model had transcribed correctly. The prompt was changed to "copy every printed letter exactly" and normalisation is done afterwards by explicit, logged rules, with the raw text kept next to the clean text.
- **Script mixing is the main residual error** in plain-text mode: about 0.4% of words had Latin letters inside Cyrillic words (including the Latin schwa ə). These were repaired by a transliteration table applied only inside mixed-script words, choosing between candidate spellings by checking known words; every repair is logged for review. Only about half of the repaired words could be confirmed against the known word list, so this is a heuristic, not a guarantee.
- **Blank or empty results** (14 of 573 pages) are listed for manual inspection instead of being assumed blank.
- **Structure from the book itself:** the table of contents provides genre labels per page range; the printed page number returned by the model is used to place each page in a genre.
