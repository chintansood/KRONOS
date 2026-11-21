"""Fetch real High Court criminal-petition orders (open data, CC-BY-4.0) and build the pseudonymised public-records dataset.
Run with an isolated interpreter (downloaded files are untrusted data):
    .venv/bin/python -I scripts/fetch_public_records.py --target 40
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kronos.realdata import build

ap = argparse.ArgumentParser()
ap.add_argument("--target", type=int, default=40)
ap.add_argument("--max-fetch", type=int, default=260)
a = ap.parse_args()
docs, stats = build.collect(target=a.target, max_fetch=a.max_fetch, cache=ROOT / "data/external/hc_pdfs")
res = build.to_dataset(docs, ROOT / "data/public_records")
report = {"source": "Indian High Court Judgments open dataset (AWS Open Data; Dattam Labs; eCourts) — CC-BY-4.0",
          "court": "High Court of Punjab and Haryana", "selection": "CRM-M petitions (bail / quashing) by private parties vs State of Punjab/Haryana/UT Chandigarh, decided 2024-2025, random order",
          "fetch": stats, "dataset": res}
(ROOT / "data/public_records/report.json").write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
