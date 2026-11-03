"""
Run OCR over every PDF in a folder, one after another, and stop cleanly when the daily limit is hit.
Run the same command every day: finished pages are skipped, so it simply continues.

    python run_all.py --folder /content/drive/MyDrive/OCR/volumes --out-root /content/drive/MyDrive/OCR/results
    (add --mode text for folklore / prose, and --model to change the model)
"""
import argparse
import glob
import os
import subprocess
import sys

import pymupdf as fitz

ap = argparse.ArgumentParser()
ap.add_argument("--folder", required=True)
ap.add_argument("--out-root", required=True)
ap.add_argument("--model", default="gemini-3.5-flash-lite")
ap.add_argument("--mode", default="dict", choices=["dict", "text"])
ap.add_argument("--sleep", default="6")
args = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
pdfs = sorted(glob.glob(os.path.join(args.folder, "*.pdf")))
if not pdfs:
    sys.exit("No PDF files found in " + args.folder)
for pdf in pdfs:
    name = os.path.splitext(os.path.basename(pdf))[0]
    out = os.path.join(args.out_root, name)
    total = len(fitz.open(pdf))
    done = len(glob.glob(os.path.join(out, "page_*.json")))
    print(f"\n=== {name}: {done}/{total} pages done ===", flush=True)
    if done >= total:
        continue
    cmd = [sys.executable, "-u", os.path.join(here, "ocr_dict.py"), pdf, "--out", out, "--model", args.model,
           "--mode", args.mode, "--sleep", args.sleep]
    stop = False
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as p:
        for line in p.stdout:
            print(line, end="", flush=True)
            if "Daily limit reached" in line or line.startswith("Stopping:"):
                stop = True
    if stop:
        print("\nStopped for today. Run the same command again later: it continues where it stopped.")
        break
print("\nAll finished (or stopped). Results are in:", args.out_root)
