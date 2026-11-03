"""
Quality control and human review helpers for the Karakalpak OCR pipeline.
Used from the Colab notebook (Karakalpak_OCR.ipynb), but every function also works from plain Python.

What it does
  1. build_report: scans the OCR result files and flags pages that probably contain errors
  2. pick_pages:   chooses pages for review (the most suspicious ones, a random sample, or both)
  3. review:       shows the page image next to the recognised text; you press OK / Errors / Redo
  4. redo_pages:   re-runs the pages you marked "redo" (optionally with a stronger model)
  5. accuracy_summary: turns your checks on a RANDOM sample into an accuracy estimate for the README
"""
import collections
import csv
import glob
import html
import io
import itertools
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

try:
    import pymupdf as fitz
except ImportError:  # older versions
    import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
KK = set("абвгғдеёжзийкқлмнңоөпрстуүўфхҳцчшщъыьэюяә")
LATIN = re.compile(r"[A-Za-zəƏıİ]+")
ROMAN = re.compile(r"^[IVXLCivxlc]+$")
WORD = re.compile(r"[а-яёәғқңөүўҳұһ]+(?:-[а-яёәғқңөүўҳұһ]+)*", re.I)
HEAD_RE = re.compile(r"^[А-ЯЁ0-9][А-ЯЁ0-9 .\-]{3,}\s", re.M)
SUB = {"р": "ғ", "к": "қ", "н": "ң", "у": "ўү", "э": "ә", "о": "ө", "х": "ҳ"}


# ------------------------------------------------------------------ loading
def load_results(result_dir):
    out = {}
    for f in glob.glob(os.path.join(result_dir, "page_*.json")):
        try:
            p = int(os.path.basename(f)[5:9])
            out[p] = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return out


def load_vocab(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        return {}
    vocab = {}
    for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
        try:
            vocab[r["word"].lower()] = int(r["frequency"])
        except (KeyError, ValueError):
            pass
    return vocab


def texts_of(d, mode):
    """All text fields of a page as a list of strings."""
    if mode == "text":
        return [d.get("text") or ""]
    out = []
    for e in d.get("entries") or []:
        out.append(e.get("headword") or "")
        for s in e.get("senses") or []:
            out.append(s.get("definition") or "")
            out += [x.get("text") or "" for x in s.get("examples") or []]
        for ph in e.get("phraseology") or []:
            out.append((ph.get("phrase") or "") + " " + (ph.get("definition") or ""))
            out += [x.get("text") or "" for x in ph.get("examples") or []]
    return out


# ------------------------------------------------------------------ checks
def _variants(w):
    pos = [i for i, ch in enumerate(w) if ch in SUB]
    out = set()
    for k in (1, 2):
        for comb in itertools.combinations(pos, k):
            for rep in itertools.product(*[SUB[w[i]] for i in comb]):
                v = list(w)
                for i, c in zip(comb, rep):
                    v[i] = c
                out.add("".join(v))
    return out


def find_suspect_words(freq, vocab=None):
    """Rare spellings whose variant with special letters (ғ қ ң ү ў ә ө ҳ) is much more frequent."""
    vocab = vocab or {}
    score = lambda w: freq.get(w, 0) + 3 * vocab.get(w, 0)  # noqa: E731
    sus = {}
    for w, c in freq.items():
        if c > 2 or len(w) < 4 or "-" in w:
            continue
        best = None
        for v in _variants(w):
            s = score(v)
            if s >= 6 and s >= 8 * max(score(w), 1) and (best is None or s > best[1]):
                best = (v, s)
        if best:
            sus[w] = best[0]
    return sus


def build_report(result_dir, pdf_path=None, mode="dict", vocab_csv=None, allowed_extra=None, save_to=None):
    """Return a list of rows (one per page), most suspicious first, and optionally save them as CSV."""
    if allowed_extra is None:
        allowed_extra = "ұһ" if mode == "text" else ""
    results = load_results(result_dir)
    if not results:
        raise SystemExit("No page_*.json files in " + result_dir)
    vocab = load_vocab(vocab_csv)
    freq = collections.Counter()
    for d in results.values():
        for t in texts_of(d, mode):
            freq.update(w.lower() for w in WORD.findall(t))
    suspects = find_suspect_words(freq, vocab)
    doc = fitz.open(pdf_path) if pdf_path and os.path.exists(pdf_path) else None

    chars = {p: sum(len(t) for t in texts_of(d, mode)) for p, d in results.items()}
    nonempty = sorted(c for c in chars.values() if c > 0)
    median_chars = nonempty[len(nonempty) // 2] if nonempty else 0

    rows = []
    for p in sorted(results):
        d = results[p]
        ts = texts_of(d, mode)
        flags, bad_words, score = [], [], 0
        n_items = len([x for x in (d.get("text") or "").splitlines() if x.strip()]) if mode == "text" \
            else sum(1 for e in d.get("entries") or [] if e.get("headword"))
        layer = ""
        if doc is not None and 1 <= p <= len(doc):
            ptxt = doc[p - 1].get_text()
            if mode == "dict":
                layer = len(HEAD_RE.findall(ptxt))
            if chars[p] == 0 and len(ptxt.strip()) > 300:
                flags.append("empty result but the page has text"); score += 10
        elif chars[p] == 0:
            flags.append("empty result"); score += 3
        if mode == "dict" and layer != "" and layer >= 4 and n_items + 2 < layer:
            flags.append(f"fewer entries ({n_items}) than text layer ({layer})"); score += 6
        # Latin letters inside the text (Roman numerals are fine)
        lat = [m.group(0) for t in ts for m in LATIN.finditer(t) if not ROMAN.match(m.group(0))]
        if lat:
            flags.append(f"Latin letters x{len(lat)}"); score += min(2 * len(lat), 8); bad_words += lat
        # letters that do not belong to the alphabet of this edition
        allowed = KK | set(allowed_extra)
        odd = [c for t in ts for c in t.lower() if c.isalpha() and c not in allowed and not LATIN.match(c)]
        if odd:
            flags.append("odd letters " + "".join(sorted(set(odd)))); score += min(len(odd), 4)
        # rare spellings with a much more frequent special-letter variant
        sw = [w for t in ts for w in (x.lower() for x in WORD.findall(t)) if w in suspects]
        if sw:
            flags.append(f"suspect spellings x{len(sw)}"); score += min(len(sw), 6); bad_words += sw
        # uncertainty marks and stray combining marks
        unc = sum(t.count("[?]") for t in ts) + sum(bool(e.get("uncertain")) for e in d.get("entries") or [])
        if unc:
            flags.append(f"uncertain x{unc}"); score += min(2 * unc, 4)
        mn = sum(1 for t in ts for c in t if unicodedata.category(c) == "Mn")
        if mn:
            flags.append(f"stray marks x{mn}"); score += min(mn, 3)
        if mode == "text" and median_chars and 0 < chars[p] < 0.3 * median_chars:
            flags.append("much shorter than typical page"); score += 2
        rows.append({"pdf_page": p, "printed_page": d.get("printed_page"), "items": n_items, "chars": chars[p],
                     "layer_headwords": layer, "score": score, "flags": "; ".join(flags),
                     "suspicious_words": " ".join(dict.fromkeys(bad_words))[:200]})
    rows.sort(key=lambda r: (-r["score"], r["pdf_page"]))
    if save_to:
        with open(save_to, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return rows


def pick_pages(rows, how="flagged", n=15, seed=7, min_score=2):
    """how = 'flagged' (most suspicious), 'random' (unbiased sample) or 'both' (half each)."""
    flagged = [r["pdf_page"] for r in rows if r["score"] >= min_score]
    pool = [r["pdf_page"] for r in rows if r["chars"] > 0]
    rnd = random.Random(seed)
    if how == "flagged":
        return flagged[:n]
    if how == "random":
        return sorted(rnd.sample(pool, min(n, len(pool))))
    half = max(1, n // 2)
    rand = sorted(rnd.sample(pool, min(half, len(pool))))
    rest = [p for p in flagged if p not in rand][: n - len(rand)]
    return rand + rest


def pick_labels(rows, how="both", n=12, seed=7, min_score=2):
    """Like pick_pages, but returns {page: 'random' or 'flagged'} (the dict keeps the order)."""
    pages = pick_pages(rows, how, n, seed, min_score)
    flagged = {r["pdf_page"] for r in rows if r["score"] >= min_score}
    if how == "random":
        return {p: "random" for p in pages}
    if how == "flagged":
        return {p: "flagged" for p in pages}
    half = max(1, n // 2)
    return {p: ("random" if i < half else "flagged") for i, p in enumerate(pages)}


# ------------------------------------------------------------------ decisions
FIELDS = ["pdf_page", "status", "checked_words", "wrong_words", "sample", "note", "time"]


def load_decisions(path):
    out = {}
    if path and os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            try:
                out[int(r["pdf_page"])] = r
            except (KeyError, ValueError):
                pass
    return out


def save_decision(path, page, status, checked=0, wrong=0, sample="", note=""):
    dec = load_decisions(path)
    dec[page] = {"pdf_page": page, "status": status, "checked_words": checked, "wrong_words": wrong,
                 "sample": sample, "note": note, "time": time.strftime("%Y-%m-%d %H:%M")}
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for p in sorted(dec):
            w.writerow({k: dec[p].get(k, "") for k in FIELDS})


# ------------------------------------------------------------------ page display
def render_page(pdf_path, page, dpi=100):
    doc = fitz.open(pdf_path)
    return doc[page - 1].get_pixmap(dpi=dpi).tobytes("png")


def _mark(text, words):
    esc = html.escape(text)
    for w in sorted(set(words), key=len, reverse=True):
        if w:
            esc = re.sub(re.escape(html.escape(w)), lambda m: f"<mark>{m.group(0)}</mark>", esc)
    return esc


def format_page_html(d, mode, bad_words=()):
    if mode == "text":
        return "<div style='font-size:14px;line-height:1.35'>" + _mark(d.get("text") or "", bad_words).replace("\n", "<br>") + "</div>"
    parts = []
    for e in d.get("entries") or []:
        s = f"<p style='margin:4px 0'><b>{_mark(e.get('headword') or '(continues)', bad_words)}</b> <i>{html.escape(e.get('label') or '')}</i>"
        if e.get("cross_reference"):
            s += f" &rarr; {_mark(e['cross_reference'], bad_words)}"
        for sn in e.get("senses") or []:
            s += f"<br>{sn.get('number') or ''} {html.escape(sn.get('field') or '')} {_mark(sn.get('definition') or '', bad_words)}"
            for x in sn.get("examples") or []:
                src = f" ({html.escape(x['source'])})" if x.get("source") else ""
                s += f"<br>&nbsp;&nbsp;<span style='color:#555'>{_mark(x.get('text') or '', bad_words)}{src}</span>"
        for ph in e.get("phraseology") or []:
            s += f"<br><b>&loz; {_mark(ph.get('phrase') or '', bad_words)}</b> {_mark(ph.get('definition') or '', bad_words)}"
        parts.append(s + "</p>")
    return "<div style='font-size:13px'>" + "".join(parts) + "</div>"


def review(pdf_path, result_dir, pages, decisions_csv, mode="dict", rows=None, sample=""):
    """Interactive review (Colab / Jupyter). Page image on the left, recognised text on the right."""
    import ipywidgets as W
    from IPython.display import display

    results = load_results(result_dir)
    by_page = {r["pdf_page"]: r for r in (rows or [])}
    done = load_decisions(decisions_csv)
    todo = [p for p in pages if p not in done and p in results]
    if not todo:
        print("Nothing to review: all chosen pages already have a decision (see", decisions_csv + ").")
        return None
    st = {"i": 0}
    img = W.Image(format="png", width=520)
    txt = W.HTML(layout=W.Layout(width="520px", height="640px", overflow_y="auto", border="1px solid #ccc", padding="6px"))
    head = W.HTML()
    checked = W.IntText(value=10, description="Проверено слов:", style={"description_width": "120px"}, layout=W.Layout(width="200px"))
    wrong = W.IntText(value=0, description="Из них неверных:", style={"description_width": "120px"}, layout=W.Layout(width="200px"))
    note = W.Text(placeholder="заметка (необязательно)", layout=W.Layout(width="420px"))
    b_ok = W.Button(description="✓ Всё верно", button_style="success")
    b_err = W.Button(description="✎ Есть ошибки", button_style="warning")
    b_redo = W.Button(description="↻ Переделать страницу", button_style="danger")
    b_skip = W.Button(description="Пропустить")
    msg = W.HTML()

    def show():
        if st["i"] >= len(todo):
            head.value = "<h3>Готово: все выбранные страницы проверены.</h3>"
            img.value = b""
            txt.value = ""
            for b in (b_ok, b_err, b_redo, b_skip):
                b.disabled = True
            return
        p = todo[st["i"]]
        r = by_page.get(p, {})
        head.value = (f"<b>Страница {p}</b> (напечатанная {results[p].get('printed_page')}) — {st['i'] + 1} из {len(todo)}"
                      f"<br><small>{html.escape(r.get('flags') or 'без автоматических подозрений')}</small>")
        img.value = render_page(pdf_path, p)
        bad = (r.get("suspicious_words") or "").split()
        txt.value = format_page_html(results[p], mode, bad)
        checked.value, wrong.value, note.value = 10, 0, ""

    def done_with(status):
        p = todo[st["i"]]
        if status == "errors" and wrong.value <= 0:
            msg.value = "<b style='color:#b00'>Впиши, сколько слов неверны (больше 0), или нажми «Всё верно».</b>"
            return
        if status == "ok":
            wr = 0
        elif status == "redo":
            wr = wrong.value if wrong.value > 0 else checked.value   # an unusable page counts as fully wrong
        else:
            wr = wrong.value
        lab = sample.get(p, "") if isinstance(sample, dict) else sample
        save_decision(decisions_csv, p, status, checked.value, wr, lab, note.value)
        msg.value = f"сохранено: страница {p} — {status}"
        st["i"] += 1
        show()

    b_ok.on_click(lambda _: done_with("ok"))
    b_err.on_click(lambda _: done_with("errors"))
    b_redo.on_click(lambda _: done_with("redo"))
    b_skip.on_click(lambda _: (st.__setitem__("i", st["i"] + 1), show()))
    show()
    ui = W.VBox([head, W.HBox([img, txt]), W.HBox([checked, wrong, note]), W.HBox([b_ok, b_err, b_redo, b_skip]), msg])
    display(ui)
    return ui


# ------------------------------------------------------------------ OCR runner and redo
def run_ocr(pdf_path, result_dir, mode="dict", model="gemini-3.5-flash-lite", pages=None, force=False, sleep=6):
    """Run ocr_dict.py on a PDF and stream its output. Stops cleanly on the daily limit."""
    cmd = [sys.executable, "-u", os.path.join(HERE, "ocr_dict.py"), pdf_path, "--out", result_dir,
           "--mode", mode, "--model", model, "--sleep", str(sleep)]
    tmp = None
    if pages:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        tmp.write("\n".join(str(p) for p in pages))
        tmp.close()
        cmd += ["--pages", tmp.name]
    else:
        cmd += ["--start", "1", "--end", str(len(fitz.open(pdf_path)))]
    if force:
        cmd.append("--force")
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as pr:
        for line in pr.stdout:
            print(line, end="", flush=True)
    if tmp:
        os.unlink(tmp.name)


def drop_decisions(decisions_csv, statuses=("errors",)):
    """Remove decisions with the given statuses so that those pages are shown again by review()."""
    dec = load_decisions(decisions_csv)
    keep = {p: r for p, r in dec.items() if r.get("status") not in statuses}
    with open(decisions_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for p in sorted(keep):
            w.writerow({k: keep[p].get(k, "") for k in FIELDS})
    return sorted(set(dec) - set(keep))


def mark_redone(decisions_csv, result_dir):
    """After a redo run: pages whose result file is newer than the 'redo' decision become 'redone'."""
    dec = load_decisions(decisions_csv)
    changed = []
    for p, r in dec.items():
        if r.get("status") != "redo":
            continue
        f = os.path.join(result_dir, f"page_{p:04d}.json")
        try:
            t_dec = time.mktime(time.strptime(r["time"], "%Y-%m-%d %H:%M"))
        except (ValueError, KeyError):
            continue
        if os.path.exists(f) and os.path.getmtime(f) >= t_dec - 60:
            save_decision(decisions_csv, p, "redone", r["checked_words"], r["wrong_words"], r.get("sample", ""), r.get("note", ""))
            changed.append(p)
    return changed


def redo_pages(decisions_csv):
    return sorted(p for p, r in load_decisions(decisions_csv).items() if r.get("status") == "redo")


# ------------------------------------------------------------------ accuracy
def _wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - a) / d), min(1.0, (c + a) / d))


def accuracy_summary(decisions_csv):
    dec = load_decisions(decisions_csv)
    if not dec:
        print("No decisions yet.")
        return
    print("Страниц проверено:", len(dec), dict(collections.Counter(r["status"] for r in dec.values())))

    def counts(r):
        chk = int(r["checked_words"] or 0)
        wr = int(r["wrong_words"] or 0)
        if r["status"] in ("redo", "redone") and wr == 0:
            wr = chk                      # a page marked unusable counts as fully wrong
        return chk, wr

    missing = [p for p, r in dec.items() if r["status"] == "errors" and int(r["wrong_words"] or 0) == 0]
    if missing:
        print(f"ВНИМАНИЕ: у страниц {sorted(missing)} стоит «Есть ошибки», но число неверных слов не указано (0). "
              "Оценка занижена. Запусти ocr_qa.drop_decisions(DECISIONS) и проверь эти страницы заново.")
    for label in ("random", "flagged"):
        rs = [r for r in dec.values() if r.get("sample") == label]
        n = sum(counts(r)[0] for r in rs)
        k = sum(counts(r)[1] for r in rs)
        unusable = sum(1 for r in rs if r["status"] in ("redo", "redone"))
        if n:
            lo, hi = _wilson(k, n)
            title = "СЛУЧАЙНАЯ выборка (для README)" if label == "random" else "подозрительные страницы (не показатель качества)"
            print(f"{title}: {len(rs)} стр., {n} слов, неверных {k} = {100 * k / n:.1f}% "
                  f"(95% интервал {100 * lo:.1f}-{100 * hi:.1f}%); непригодных страниц (переделка): {unusable} из {len(rs)}")
    redo = sorted(p for p, r in dec.items() if r["status"] == "redo")
    if redo:
        print("Страницы на переделку:", redo)
    redone = sorted(p for p, r in dec.items() if r["status"] == "redone")
    if redone:
        print("Переделаны, но ещё не проверены заново:", redone, "(ocr_qa.drop_decisions(DECISIONS, ('redone',)) вернёт их в очередь проверки)")
    if not any(r.get("sample") == "random" for r in dec.values()):
        print("Честную оценку точности даёт только случайная выборка: запусти проверку со способом 'random' или 'both'.")
