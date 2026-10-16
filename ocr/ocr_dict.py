"""
OCR of the Karakalpak explanatory dictionary (scanned PDF) via the Gemini API.

One page per request. Each result is saved as its own JSON file, so you can stop
and resume at any time (finished pages are skipped).

Setup (once):
    pip install google-genai pymupdf
    Windows PowerShell:  $env:GEMINI_API_KEY="your_key"
    Mac / Linux:         export GEMINI_API_KEY="your_key"

Run (PDF page numbers, starting from 1):
    python ocr_dict.py "dictionary_vol1.pdf" --start 102 --end 111 --out out_vol1

List the model names your key can use:
    python ocr_dict.py --list-models
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Optional

try:
    import pymupdf as fitz
except ImportError:  # older versions
    import fitz
from google import genai
from google.genai import types
from pydantic import BaseModel


# ---------- output schema ----------
class Example(BaseModel):
    text: str
    source: Optional[str] = None


class Sense(BaseModel):
    number: Optional[int] = None
    field: Optional[str] = None
    definition: str
    examples: list[Example] = []


class Phraseme(BaseModel):
    phrase: str
    definition: str
    examples: list[Example] = []


class Entry(BaseModel):
    headword: Optional[str] = None
    label: Optional[str] = None
    senses: list[Sense] = []
    phraseology: list[Phraseme] = []
    cross_reference: Optional[str] = None
    continues_from_previous: bool = False
    continues_on_next: bool = False
    uncertain: bool = False


class Page(BaseModel):
    printed_page: Optional[str] = None
    entries: list[Entry] = []


class TextPage(BaseModel):
    printed_page: Optional[str] = None
    text: str = ""


PROMPT = """You are an expert OCR transcriber of printed Karakalpak (Cyrillic) dictionary pages.
The image is ONE page of the explanatory dictionary "Qaraqalpaq tilinin tusindirme sozligi".
Transcribe EVERY entry on the page, from the top to the bottom. Do not skip or merge entries.

LETTERS: Karakalpak uses special Cyrillic letters. Read each one from the image and never
replace it with a Russian look-alike:
  ә (not э), ғ (not р), қ (not к), ң (not н), ө (not о), ү (not у), ў (not у), ҳ (not х).
  The sequence ңғ (as in АЛДЫҢҒЫ) is NOT "нг". The letter ғ is NOT "р".
Copy exactly what is printed. Do not correct spelling, do not translate, do not invent text.

LAYOUT:
- Headwords are printed in bold capitals and start a new entry. Put the headword in "headword".
- Copy the part-of-speech label exactly as printed (ат., ф., р., кел., к.с., ...) into "label".
- Senses are numbered in bold (1., 2., 3.). Optional field labels (дин., ауыс., мед., ...)
  go into "field".
- Italic sentences are examples. The author or source in parentheses goes into "source".
- Bold phrases inside an entry (often after a diamond sign or after the senses) are idioms /
  phraseological units. Put each into "phraseology" with its definition and examples.
  Do NOT drop them.
- If the entry is only "к." plus another word, put that word into "cross_reference".
- If the page starts in the middle of an entry, set headword to null and
  continues_from_previous to true. If the last entry continues on the next page, set
  continues_on_next to true.
- Read the printed page number at the bottom into "printed_page" (null if absent).
- Ignore running headers and decorations.

SCRIPT: write everything in Cyrillic. NEVER use Latin letters or transliteration
(not even for a single letter inside a word). The only allowed Latin characters are Roman numerals
(I, II, III) after a homonym headword, e.g. "СЫР II". Do not add combining marks (breve etc.);
write Ў, Ү, Ө, Ң, Ғ, Қ, Ҳ, Ә as single letters.

UNCERTAINTY: if a character or word is unclear, write your best reading followed by [?]
and set "uncertain" to true for that entry. Never silently guess.
Return only JSON that matches the schema."""


PROMPT_TEXT = """You are an expert OCR transcriber of printed Karakalpak (Cyrillic) texts: folklore, epics,
poems, prose. The image is ONE page. Transcribe ALL running text of the page exactly as printed,
from top to bottom, keeping line breaks for verse and paragraph breaks for prose (use \\n).

LETTERS: Karakalpak uses special Cyrillic letters. Read each one from the image and never replace it
with a Russian look-alike: ә (not э), ғ (not р), қ (not к), ң (not н), ө (not о), ү (not у),
ў (not у), ҳ (not х). Copy exactly what is printed. Do not correct spelling, do not translate,
do not invent or complete text.

SCRIPT: write everything in Cyrillic. NEVER use Latin letters or transliteration. Do not add
combining marks (breve etc.); write Ў, Ү, Ө, Ң, Ғ, Қ, Ҳ, Ә as single letters.

Put the page number printed at the bottom or top into "printed_page" (null if absent) and do NOT include
it, running headers, or footnote numbers in "text". Keep titles and verse numbers as printed.
If a character or word is unclear, write your best reading followed by [?].
Return only JSON that matches the schema."""


HEADWORD_RE = re.compile(r"^[А-ЯЁ0-9][А-ЯЁ0-9 .\-]{3,}\s", re.M)


class QuotaStop(Exception):
    pass


class ServerBusy(Exception):
    pass


def call_model(client, model, img_bytes, prompt=PROMPT, schema=Page):
    for attempt in range(5):
        try:
            return client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                if "PerDay" in msg or "per day" in msg.lower():
                    raise QuotaStop(msg)  # real daily limit: stop for today
                print("  per-minute rate limit, waiting 65 s ...")
                time.sleep(65)
                continue
            if "503" in msg or "UNAVAILABLE" in msg or "500" in msg or "overloaded" in msg.lower():
                wait = 20 * (attempt + 1)
                print(f"  model is busy (503), waiting {wait} s ...")
                time.sleep(wait)
                continue
            raise
    raise ServerBusy("model stayed unavailable or rate limited after 5 attempts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--start", type=int, default=1, help="first PDF page (1-based)")
    ap.add_argument("--end", type=int, default=None, help="last PDF page (1-based)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--model", default="gemini-3.6-flash")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--sleep", type=float, default=6.0, help="pause between requests, seconds")
    ap.add_argument("--pages", default=None, help="comma list of PDF pages or a .txt file with one page per line (overrides --start/--end)")
    ap.add_argument("--mode", choices=["dict", "text"], default="dict",
                    help="dict = dictionary entries (JSON structure); text = plain running text (folklore, prose, verse)")
    ap.add_argument("--list-models", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Set the GEMINI_API_KEY environment variable first (see the top of this file).")
    client = genai.Client(api_key=key)

    if args.list_models:
        for m in client.models.list():
            print(m.name)
        return
    if not args.pdf:
        sys.exit("Give the PDF path.")

    os.makedirs(args.out, exist_ok=True)
    doc = fitz.open(args.pdf)
    last = min(args.end or len(doc), len(doc))
    log_path = os.path.join(args.out, "log.csv")
    new_log = not os.path.exists(log_path)
    log = open(log_path, "a", newline="", encoding="utf-8")
    writer = csv.writer(log)
    if new_log:
        writer.writerow(["pdf_page", "printed_page", "entries", "layer_headwords",
                         "input_tokens", "output_tokens", "warning"])

    if args.pages:
        if os.path.exists(args.pages):
            page_list = [int(x) for x in open(args.pages).read().replace(",", "\n").split() if x.strip()]
        else:
            page_list = [int(x) for x in args.pages.split(",") if x.strip()]
    else:
        page_list = list(range(args.start, last + 1))

    done = 0
    for n in page_list:
        path = os.path.join(args.out, f"page_{n:04d}.json")
        if os.path.exists(path):
            continue
        page = doc[n - 1]
        img = page.get_pixmap(dpi=args.dpi).tobytes("jpeg")
        print(f"page {n} ...")
        try:
            if args.mode == "text":
                resp = call_model(client, args.model, img, PROMPT_TEXT, TextPage)
            else:
                resp = call_model(client, args.model, img)
        except QuotaStop as e:
            print("Daily limit reached for this model. Details from Google:")
            print("  " + str(e)[:600])
            print("Run the same command tomorrow (finished pages are skipped) or try another --model.")
            break
        except ServerBusy as e:
            print(f"Stopping: {e}.")
            print("Try again in 10-30 minutes, or pick another model with --model (see --list-models).")
            break
        except Exception as e:  # noqa: BLE001
            print(f"  error on page {n}: {e}")
            writer.writerow([n, "", "", "", "", "", f"error: {str(e)[:120]}"])
            continue
        if not resp.text:
            print(f"  empty response on page {n} (blocked or no text)")
            writer.writerow([n, "", "", "", "", "", "empty response"])
            continue

        try:
            data = json.loads(resp.text)
        except ValueError:
            print(f"  unreadable JSON on page {n}, will be retried next run")
            writer.writerow([n, "", "", "", "", "", "bad json"])
            continue
        data = {"pdf_page": n, "model": args.model, **data}
        if args.mode == "dict" and not data.get("entries") and len(page.get_text().strip()) > 300:
            print(f"  no entries on page {n}, not saved (will be retried next run)")
            writer.writerow([n, "", 0, "", "", "", "no entries"])
            continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        u = resp.usage_metadata
        if args.mode == "text":
            lines = len([x for x in (data.get("text") or "").splitlines() if x.strip()])
            writer.writerow([n, data.get("printed_page"), lines, "", getattr(u, "prompt_token_count", ""),
                             getattr(u, "candidates_token_count", ""), ""])
            print(f"  ok: {lines} lines")
        else:
            # completeness check against the (garbled but structurally reliable) PDF text layer
            layer = len(HEADWORD_RE.findall(page.get_text()))
            got = sum(1 for e in (data.get("entries") or []) if e.get("headword"))
            warn = "CHECK: fewer entries than text layer" if layer and got + 2 < layer else ""
            writer.writerow([n, data.get("printed_page"), got, layer, getattr(u, "prompt_token_count", ""),
                             getattr(u, "candidates_token_count", ""), warn])
            print(f"  ok: {got} entries (text layer: {layer}) {warn}")
        log.flush()
        done += 1
        time.sleep(args.sleep)

    log.close()
    print(f"Done. New pages this run: {done}. Results and log.csv are in: {args.out}")


if __name__ == "__main__":
    main()
