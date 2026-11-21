"""Second-line privacy check of the pseudonymised public records, using the local LLM (nothing leaves the machine).

The model is asked to list any personal names of real individuals still present in each narrative. Every reported
name that literally occurs in the text (outside the [Label] placeholders) is masked as a neutral [Name Rn] label, and
the counts are written to report.json — they measure how much the rule-based layers missed.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from ..config import settings
from ..engines.llm import ollama

PROMPT = ("You check court-record extracts for leftover personal names. The text has already been pseudonymised: labels in "
          "square brackets such as [Accused A1] or [Name W2] are NOT names. List every remaining name of a real individual "
          "person (not places, police stations, districts, organisations, statutes or brands). Reply with JSON: "
          '{"names": ["..."]} — an empty list if there are none.')


def audit(d: Path | None = None) -> dict:
    d = Path(d or settings.public_records_dir)
    f = d / "PUBLIC_FIR.csv"
    rows = list(csv.DictReader(open(f, newline="", encoding="utf-8")))
    found_total, masked_total, per_case = 0, 0, {}
    for r in rows:
        text = r["narrative"]
        body = re.sub(r"^\[Public record[^\]]*\]\s*", "", text)
        try:
            out = ollama.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": body[:3500]}],
                              max_tokens=200, temperature=0, json_mode=True)
            names = [n for n in json.loads(out).get("names", []) if isinstance(n, str)]
        except (ollama.LLMUnavailable, ValueError, AttributeError):
            return {"error": "local LLM unavailable — audit not run"}
        visible = re.sub(r"\[[^\]]*\]", " ", body)
        hits = [n.strip() for n in names if len(n.strip()) >= 3 and re.search(rf"\b{re.escape(n.strip())}\b", visible)]
        found_total += len(hits)
        k = 0
        for n in sorted(set(hits), key=len, reverse=True):
            k += 1
            text, m = re.subn(rf"(?<!\[)\b{re.escape(n)}\b(?![^\[]*\])", f"[Name R{k}]", text)
            masked_total += m
        r["narrative"] = text
        if hits:
            per_case[r["case_id"]] = len(set(hits))
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    res = {"model": ollama.model_name(), "records": len(rows), "recordsWithLeftoverNames": len(per_case),
           "leftoverNamesFound": found_total, "occurrencesMasked": masked_total, "byCase": per_case}
    rep = d / "report.json"
    j = json.loads(rep.read_text()) if rep.exists() else {}
    j["piiAudit"] = res
    rep.write_text(json.dumps(j, indent=1))
    return res
