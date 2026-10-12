# Karakalpak-NLP

Building NLP resources and tools for the low-resource Karakalpak language — starting with corpus collection.

## About the Project
This repository is dedicated to creating structured NLP datasets, preprocessing pipelines, and language tools for the Karakalpak language. Since Karakalpak is a low-resource language, this project aims to bridge the gap by digitizing both modern texts (news, Wikipedia) and traditional literary works (dastans).

## Project Structure
- `data/raw/` — Raw text files divided into `modern` and `traditional` literature.
- `data/processed/` — Cleaned and preprocessed corpora.
- `notebooks/` — Jupyter notebooks for data extraction, OCR, cleaning, and analytics.
- `src/` — Python scripts and source code for pipelines and tokenizers.
- `docs/` — Project documentation.

## Roadmap

### Completed 
1. **Corpus Collection** — 3 classic Karakalpak dastans (Qiriq Qiz, Qoblan, Er Ziyar)
2. **Data Extraction** — extracted text from PDFs and TXT files
3. **Frequency Analysis** — 17,293 unique words, frequency vocabulary
4. **Sentiment Lexicon** — manual annotation of sentiment for all words
5. **Sentiment Analysis** — compared emotional tone across 3 dastans
6. **Interactive Dictionary** — live web app with Cyrillic and Latin search
   → huggingface.co/spaces/nietbaeviysa/karakalpak-dictionary

### In Progress 
7. **Comparative Analysis** — Karakalpak vs Uzbek language comparison
8. **Modern Texts** — adding contemporary Karakalpak digital texts

### Planned 📋
9. **Tokenizer** — custom tokenizer for Karakalpak language
10. **Baseline NLP Models** — first ML models for Karakalpak
## Published Datasets
- Hugging Face: huggingface.co/datasets/nietbaeviysa/karakalpak-dastan-corpus
- Kaggle: kaggle.com/datasets/nietbaeviysa/karakalpak-dastan-corpus

- ## Notebooks
- `frequency_analysis.ipynb` — frequency analysis, 17,293 unique words
- `sentiment_analysis.ipynb` — sentiment analysis of 3 dastans

## Key Findings
- Qiriq Qiz: most positive dastan (2.9% positive, 0.9% negative)
- Qoblan: balanced (2.6% positive, 1.2% negative)  
- Er Ziyar: darkest dastan (2.4% positive, 1.3% negative)

- karakalpak-dictionary v3.0 — search in both Cyrillic and Latin scripts
  huggingface.co/spaces/nietbaeviysa/karakalpak-dictionary
