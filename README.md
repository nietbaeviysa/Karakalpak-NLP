# Karakalpak NLP

Open resources and tools for **Karakalpak (Qaraqalpaq)**, a low-resource Turkic language written in Cyrillic and Latin.

Author: **Iysa Nietbaev**, English Philology student at Karakalpak State University (Nukus, Karakalpakstan, Uzbekistan). Founder of the education initiative Jeke Umid.
Goal: build open, documented language resources and grow them into a research path in computational linguistics / NLP.

## Resources

| Resource | Link |
|---|---|
| Dastan corpus (4 files) | [Hugging Face dataset](https://huggingface.co/datasets/nietbaeviysa/karakalpak-dastan-corpus) |
| Interactive dictionary (Cyrillic + Latin, examples from the dastans) | [Hugging Face Space](https://huggingface.co/spaces/nietbaeviysa/karakalpak-dictionary) |
| Corpus mirror | [Kaggle dataset](https://www.kaggle.com/datasets/nietbaeviysa/karakalpak-dastan-corpus) |
| Code and notebooks | this repository |

## Projects

| # | Project | Result |
|---|---|---|
| 1 | Word-frequency analysis of three dastans (*Qirq qiz*, *Qoblan*, *Er Ziyar*) | 17,293 unique words, CSV |
| 2 | Sentiment lexicon (positive / negative / neutral per word) | `karakalpak_sentiment_lexicon.csv` |
| 3 | Sentiment analysis of the dastans (lexicon-based) | *Qirq qiz* is the most positive (2.9%), *Er Ziyar* the darkest (1.3% negative words); see [Limitations](#quality-and-limitations-read-this-before-using-any-numbers) |
| 4 | Interactive web dictionary with examples from the dastans | live Space, works in Cyrillic and Latin |
| 5 | Corpus extension from kaa.wikipedia.org | 52 documents, 937,525 characters, ~156,000 words |
| 6 | **OCR pipeline for printed Karakalpak** (new) | one volume of an explanatory dictionary digitised; [details below](#project-6-ocr-pipeline-for-printed-karakalpak) and in [docs/OCR_PIPELINE.md](docs/OCR_PIPELINE.md) |
| 7 | **Folklore collection digitised** (*Qaraqalpaq folklori*, vols. 88-100, Nukus: Ilim, 2015), plain-text mode | 554 text pages, ~149,000 words, ~36,000 distinct word forms; proverbs, verse sayings, poets' contests, riddles, children's folklore; details in [Project 7](#project-7-folklore-collection) |
| 8 | Karakalpak vs Uzbek comparative analysis | planned |

## Project 6: OCR pipeline for printed Karakalpak

Most printed Karakalpak material exists only as scanned PDFs. The scans I worked with carry an automatic text layer, but it is unusable for NLP: the OCR engine treated the text as Russian, so letters specific to Karakalpak were replaced (ә→э, ғ→р, қ→к, ң→н, ө→о, ү/ў→у). I built a page-by-page pipeline that reads the page images with a vision language model and returns **structured JSON** instead of plain text.

First target: one volume (505 pages) of the *Explanatory Dictionary of the Karakalpak Language*.

| Measure | Value |
|---|---|
| Pages processed | 505 (499 with dictionary entries; the rest are title, table of contents and back matter) |
| Entries (headwords) | ~6,500 |
| Senses / idioms (phraseological units) | ~7,900 / ~800 |
| Usage examples with author attribution | ~3,200 |
| Running text | ~114,000 tokens, ~34,000 distinct word forms (includes residual OCR noise) |
| Cost | free API tier; ~1,600 input and ~1,900 output tokens per page |
| Measured word accuracy | 96.0% of checked words correct (manual check of 150 words on 15 random pages; 95% interval 91.5-98.2%) |

### What the pipeline does

1. Renders each PDF page to an image and sends **one page per request** (a whole-file request skipped pages in my first test).
2. Asks for a strict JSON schema: headword, label, numbered senses, examples with sources, idioms, cross-references, uncertainty flags.
3. Saves every page as its own file, so a run can be stopped and resumed; handles rate limits and server overload.
4. Post-processes the result: merges entries that continue across pages, fixes a recurring formulaic definition pattern, applies conservative letter corrections based on word frequencies, normalises Unicode and detects Latin-script contamination, which is re-run with a stricter prompt.

Details, failure modes and lessons: [docs/OCR_PIPELINE.md](docs/OCR_PIPELINE.md).

### Quality and limitations (read this before using any numbers)

- **Not fully verified.** The output is machine-read. Errors found so far include wrong special letters (for example ғ read as р), occasional dropped entries and sentences, and Latin letters inside Cyrillic words. 
- **Measured on a random sample.** 15 pages were drawn at random from the dictionary volume; on each, 10 words (mostly words with Karakalpak-specific letters, so harder than average text) were compared by the author with the printed page. 6 of 150 words were wrong: **4.0%** (95% Wilson interval 1.8-8.5%). None of the 15 pages was unusable. This measures letter-level errors on the checked words; it does not measure lost entries, which are caught only by the automatic checks. A few pages flagged by those checks (empty or garbled results) are re-processed.
- **Folklore collection, measured the same way:** 10 of 150 checked words were wrong, **6.7%** (95% Wilson interval 3.7-11.8%), none of the 15 random pages unusable. This was measured on the raw model output, before the cleaning step that repairs Latin letters inside Cyrillic words; differences in the spelling of ұ/һ were not counted as errors. The cleaned corpus has not been measured separately.
- Automatic letter correction only catches errors where the correct spelling is frequent; rare words can still be wrong.
- Models sometimes "correct" printed spelling towards an expected form, so the output is not a diplomatic transcription.
- The sentiment results (Project 3) come from a lexicon-based method without a gold-standard validation set. Treat the percentages as exploratory.
- The dastan corpus is small and comes from three epic texts, so it is not representative of modern Karakalpak.

## Project 7: Folklore collection

A second source digitised with the same pipeline in plain-text mode: a multi-volume edition of Karakalpak folklore (small genres), 573 scanned pages. Each page keeps its printed page number and a genre label taken from the book's table of contents.

| Measure | Value |
|---|---|
| Text pages | 554 (plus 13 image-only pages, title, contents and imprint) |
| Running text | ~149,000 words, ~36,000 distinct word forms (includes residual OCR noise) |
| Genres | proverbs (4 thematic parts), verse sayings, reflective verse, poets' contests, riddles, tongue twisters, lullabies, children's word art and games |
| Glossary | ~1,400 headword–explanation pairs extracted from the book's glossary of rare words |
| Overlap with the dastan word list | ~60% of the tokens; ~78% of the distinct forms are new relative to the dastans |
| Measured word accuracy (raw OCR output) | 93.3% of checked words correct (manual check of 150 words on 15 random pages; 95% interval 88.2-96.3%) |

Post-processing: Latin letters that crept into Cyrillic words were repaired (about 620 words, logged), the letter ұ was normalised to у and һ to ҳ (the edition prints ұ; the dastan texts do not), and every change can be traced.
Quality is checked on page samples only; see Limitations. Full text of the edition is not redistributed here.

## Data and licensing

Source scans of printed books are not redistributed here. The repository contains code, methodology and aggregate statistics. Data derived from copyrighted publications is not published until the rights situation is clear. If you are a rights holder and have concerns, please contact me.

## Reproduce

```bash
pip install google-genai pymupdf
export GEMINI_API_KEY="your key"        # Windows PowerShell: $env:GEMINI_API_KEY="your key"

# one PDF, a page range
python ocr/ocr_dict.py book.pdf --start 1 --end 50 --out out_book --model gemini-3.5-flash-lite

# plain running text instead of dictionary entries (folklore, prose, verse)
python ocr/ocr_dict.py book.pdf --mode text --out out_text

# every PDF in a folder; continues where it stopped after a daily limit
python ocr/run_all.py --folder pdfs --out-root results
```

Never commit API keys; the scripts read the key from the environment.

## Roadmap

- [x] Dastan corpus, frequency lists, sentiment lexicon, interactive dictionary
- [x] OCR pipeline and first dictionary volume
- [x] Manual evaluation of OCR quality on random page samples (dictionary volume: 4.0% wrong words; folklore collection: 6.7% before cleaning)
- [ ] Larger samples and a re-measurement of the cleaned folklore corpus
- [x] Folklore collection digitised (plain-text mode)
- [ ] Remaining dictionary volumes
- [ ] Merged lexicon with definitions; extended sentiment lexicon
- [ ] Karakalpak vs Uzbek comparative analysis (Project 8)
- [ ] Cyrillic–Latin transliteration tools and shared evaluation notes
- [ ] Statistics fundamentals (Khan Academy) to support evaluation methodology

## Contact

Iysa Nietbaev, iysastanford@gmail.com
