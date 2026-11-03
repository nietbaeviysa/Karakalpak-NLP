"""
Build a cleaned table for one dictionary volume from the OCR page files.
Steps: merge continuation entries, flat CSV, letter fixes by word frequency, stock-formula fix,
stray-character fix, Latin-inside-Cyrillic repair (logged), Unicode NFC, QA report.
Usage: python build_volume.py <folder_with_page_json> <pages_in_pdf> <tag> --out ./tables/ --vocab words.csv
(needs ocr_qa.py in the same folder)
"""
import sys, os, re, csv, json, glob, collections, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_qa as Q

def run(folder, total_pages, tag, out="./", vocab_path=""):
    pages = Q.load_results(folder)
    missing = [p for p in range(1, total_pages + 1) if p not in pages]
    # 1) merge entries (continuations glued to the previous entry)
    entries = []
    for p in sorted(pages):
        d = pages[p]
        for e in d.get("entries") or []:
            e = dict(e); e["pdf_page"] = p; e["printed_page"] = d.get("printed_page")
            e["senses"] = e.get("senses") or []; e["phraseology"] = e.get("phraseology") or []
            if not e.get("headword"):
                if entries:
                    entries[-1]["senses"] += e["senses"]; entries[-1]["phraseology"] += e["phraseology"]
                    if e.get("cross_reference") and not entries[-1].get("cross_reference"): entries[-1]["cross_reference"] = e["cross_reference"]
                continue
            entries.append(e)
    # 2) flat rows
    def ex_join(exs): return " | ".join((x.get("text") or "") + (f" ({x['source']})" if x.get("source") else "") for x in (exs or []))
    hdr = ["pdf_page", "printed_page", "headword", "label", "kind", "number", "field", "text", "examples", "cross_reference", "uncertain"]
    rows = []
    for e in entries:
        base = [e["pdf_page"], e.get("printed_page"), e["headword"], e.get("label")]
        if not e["senses"] and not e["phraseology"]:
            rows.append(base + ["xref" if e.get("cross_reference") else "empty", "", "", "", "", e.get("cross_reference"), e.get("uncertain")])
        for s in e["senses"]:
            rows.append(base + ["sense", s.get("number"), s.get("field"), s.get("definition"), ex_join(s.get("examples")), e.get("cross_reference"), e.get("uncertain")])
        for ph in e["phraseology"]:
            rows.append(base + ["idiom", "", "", (ph.get("phrase") or "") + " — " + (ph.get("definition") or ""), ex_join(ph.get("examples")), "", e.get("uncertain")])
    ix = {h: i for i, h in enumerate(hdr)}
    # 3) letter suspects from word frequencies (+ dastan vocabulary as a clean reference)
    vocab = Q.load_vocab(vocab_path)
    freq = collections.Counter()
    for r in rows:
        for col in ("headword", "text", "examples"):
            freq.update(w.lower() for w in Q.WORD.findall(str(r[ix[col]] or "")))
    sus = Q.find_suspect_words(freq, vocab)
    strength = lambda w: freq.get(w, 0) + 3 * vocab.get(w, 0)
    fix = {w: v for w, v in sus.items() if freq[w] <= 2 and strength(v) >= 20}
    log = []
    def fx(t, page, col):
        def rep(m):
            w = m.group(0); lw = w.lower()
            if lw in fix:
                s = fix[lw]; new = s.upper() if w.isupper() and len(w) > 1 else (s[0].upper() + s[1:] if w[0].isupper() else s)
                log.append((page, col, w, new, "letters")); return new
            return w
        return Q.WORD.sub(rep, str(t or ""))
    for r in rows:
        for col in ("headword", "text", "examples"): r[ix[col]] = fx(r[ix[col]], r[ix["pdf_page"]], col)
    # 4) stock formula "<verb> фейилиниң <quality> дәрежеси"
    def lev(a, b):
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1): cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ca != cb)))
            prev = cur
        return prev[-1]
    CANON = "фейилиниң"; QS = {"өзгелик", "шериклик", "өзлик", "белгисиз"}
    PAT = re.compile(r"^(?P<root>\S+)\s+(?P<tok>\S+)\s+(?P<q>\S+)\s+дәрежеси\b", re.I)
    for r in rows:
        if r[ix["kind"]] != "sense": continue
        t = r[ix["text"]]; m = PAT.match(t)
        if m and m["q"].lower().rstrip(".,") in QS and m["tok"].lower() != CANON and lev(m["tok"].lower(), CANON) <= 2:
            log.append((r[ix["pdf_page"]], "text", m["tok"], CANON, "formula")); r[ix["text"]] = t[:m.start("tok")] + CANON + t[m.end("tok"):]
    # 4b) stray look-alike characters that are not Latin letters but stand for Cyrillic ones
    CHARMAP = {"ɵ": "ө", "Ɵ": "Ө"}
    for r in rows:
        for col in ("headword", "text", "examples"):
            t = str(r[ix[col]] or "")
            if any(c in t for c in CHARMAP):
                new_t = "".join(CHARMAP.get(c, c) for c in t)
                log.append((r[ix["pdf_page"]], col, "".join(c for c in t if c in CHARMAP), "".join(CHARMAP[c] for c in t if c in CHARMAP), "charmap"))
                r[ix[col]] = new_t
    # 5) Latin letters inside Cyrillic words -> transliterated (heuristic, logged)
    PH = {'a':'а','b':'б','c':'с','d':'д','e':'е','f':'ф','g':'г','h':'х','i':'и','j':'ж','k':'к','l':'л','m':'м','n':'н','o':'о','p':'п','q':'қ','r':'р','s':'с','t':'т','u':'у','v':'в','w':'ў','x':'х','y':'у','z':'з','ı':'ы','ə':'ә'}
    TOK = re.compile(r"[A-Za-zəƏıİ\u0400-\u04FF]+"); LAT = re.compile(r"[A-Za-zəƏıİ]"); CYR = re.compile(r"[\u0400-\u04FF]")
    def conv(c): m = PH.get(c.lower(), c); return m.upper() if c.isupper() else m
    def fixlat(t, page, col):
        def rep(m):
            w = m.group(0)
            if LAT.search(w) and CYR.search(w):
                new = "".join(conv(c) if LAT.match(c) else c for c in w); log.append((page, col, w, new, "latin")); return new
            return w
        return TOK.sub(rep, str(t or ""))
    for r in rows:
        for col in ("headword", "text", "examples"): r[ix[col]] = fixlat(r[ix[col]], r[ix["pdf_page"]], col)
    # 6) Unicode NFC
    rows = [[unicodedata.normalize("NFC", str(c)) if c is not None else "" for c in r] for r in rows]
    with open(out + f"{tag}_entries_autofixed.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(rows)
    with open(out + f"{tag}_changes_log.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["pdf_page", "column", "before", "after", "rule"]); w.writerows(log)
    rep = Q.build_report(folder, None, "dict", vocab_path or None, save_to=out + f"{tag}_qa_report.csv")
    cnt = collections.Counter(l[4] for l in log)
    ROMAN = re.compile(r"^[IVXLC]+$")
    latin_left = sum(1 for r in rows for c in (r[ix["headword"]], r[ix["text"]], r[ix["examples"]]) if any(not ROMAN.match(m.group(0)) for m in re.finditer(r"[A-Za-z]+", c)))
    kinds = collections.Counter(r[ix["kind"]] for r in rows)
    print(f"[{tag}] pages with results: {len(pages)} of {total_pages} | missing: {missing}")
    print(f"[{tag}] headword entries: {len(entries)} | rows: {len(rows)} | {dict(kinds)}")
    print(f"[{tag}] changes: {dict(cnt)} | cells still containing Latin: {latin_left}")
    toks = sum(freq.values()); print(f"[{tag}] tokens: {toks} | distinct: {len(freq)}")
    top = [(r['pdf_page'], r['score'], r['flags'][:70]) for r in rep[:8]]
    print(f"[{tag}] most suspicious pages:", top)
    print(f"[{tag}] pages flagged (score>=2): {sum(r['score'] >= 2 for r in rep)} of {len(rep)}; empty results: {[r['pdf_page'] for r in rep if r['chars'] == 0]}")
    return missing
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Merge the page_*.json files of one dictionary volume into a cleaned table.")
    ap.add_argument("folder", help="folder with page_0001.json ... of one volume")
    ap.add_argument("total_pages", type=int, help="number of pages in the PDF")
    ap.add_argument("tag", help="name prefix for the output files, e.g. vol2")
    ap.add_argument("--out", default="./", help="output folder (must end with a slash)")
    ap.add_argument("--vocab", default="", help="optional CSV with columns word,frequency (clean reference word list)")
    a = ap.parse_args()
    run(a.folder, a.total_pages, a.tag, a.out, a.vocab)
