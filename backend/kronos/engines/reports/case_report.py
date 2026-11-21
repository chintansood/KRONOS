"""Draft case report and printable case diary.

The draft report is assembled from the case summary, case intelligence, hypotheses, next-best-evidence,
prior-record linkage and the evidence ledger. Every statement keeps its evidence IDs. Headings are
localised with fixed (human-written) labels; the narrative is machine-translated with identifier
protection when a non-English language is requested. It is a DRAFT for the Investigating Officer — not a
final report under BNSS s.193 — and analytical findings are indicators, not findings of guilt.
"""
from __future__ import annotations

import html
import re
from datetime import datetime

from ... import db
from ..identity import history
from ..intelligence import hypothesis, next_evidence
from ..llm import language
from ..multimodal import case_intel, summarizer
from ..provenance import ledger
from . import diary as diary_mod

def E(v) -> str:
    return "" if v is None else html.escape(str(v))


def build(case_id: str, lang: str = "en", use_llm: bool = False) -> dict:
    I = case_intel.get(case_id)
    if not I:
        raise KeyError(case_id)
    S = summarizer.generate_case_summary(case_id, use_llm=use_llm)
    o = I["overview"]
    hyp = hypothesis.analyse(case_id)
    recs = next_evidence.recommend(case_id)
    st = ledger.status()
    case_files = {r["file_name"] for r in db.query("SELECT DISTINCT file_name FROM raw_records WHERE case_id=%s", (case_id,))}
    exhibits = db.query("SELECT e.evidence_id, e.modality, e.ts, e.event_description, e.source_reliability, r.content_sha256, "
                        "r.file_name, (SELECT block_index FROM ledger_blocks b WHERE b.evidence_id=e.evidence_id AND "
                        "b.event_type='INGEST' LIMIT 1) block FROM events e JOIN raw_records r USING (source_record_id) "
                        "WHERE e.evidence_id = ANY(%s) ORDER BY e.ts", (S["importantEvidence"][:25],))
    narrative = S.get("llmNarrative") or S["detailedNarrative"]
    narrative_tr, tr_note = narrative, None
    if lang != "en":
        sents = [x for x in re.split(r"(?<=[.!?])\s+", narrative) if x.strip()]
        out, n = language.translate_lines(sents, lang)
        narrative_tr = " ".join(out)
        tr_note = f"{language.banner(lang)} {n} of {len(sents)} sentences translated."
    prior = []
    for p in S["people"]:
        for l in history.person_history(p["personId"])["priorRecords"]:
            if l["band"] in ("HIGH", "MEDIUM"):
                prior.append({"personId": p["personId"], **l})
    return {"caseId": case_id, "lang": lang, "generatedAt": datetime.now().isoformat(timespec="seconds"), "dataHash": S["dataHash"],
            "overview": {"title": o.get("title"), "fir": o.get("fir_number"), "station": o.get("police_station"),
                         "district": o.get("district"), "agency": o.get("agency_id"), "offence": o.get("offence_category"),
                         "incident": (o.get("incident_ts") or "")[:16].replace("T", " "), "incidentPlace": o.get("incident_location"),
                         "registered": (o.get("registration_ts") or "")[:16].replace("T", " "), "io": o.get("lead_investigator")},
            "briefFacts": narrative_tr, "briefFactsEnglish": narrative, "translationNote": tr_note,
            "people": S["people"], "chronology": S["chronology"], "recordCounts": S["recordCounts"],
            "exhibits": [{"evidenceId": x["evidence_id"], "type": x["modality"], "time": x["ts"].strftime("%d %b %Y %H:%M") if x["ts"] else "",
                          "description": x["event_description"], "reliability": x["source_reliability"],
                          "sha256": x["content_sha256"], "ledgerBlock": x["block"], "file": x["file_name"]} for x in exhibits],
            "findings": {"financial": S["financialSummary"], "communication": S["communicationSummary"],
                         "location": S["locationSummary"], "travel": S["travelInconsistencies"],
                         "observations": S["suspiciousObservations"]},
            "hypotheses": hyp.get("hypotheses", []), "pending": recs[:10], "priorRecords": prior,
            "uncertainties": S["uncertainties"], "missing": S["missingInformation"],
            "integrity": {"chainValid": st["chain"]["valid"], "blocks": st["chain"]["blocks"],
                          "anchors": [a for a in st["anchors"] if a["file"] in case_files]}}


CSS = """body{font-family:Georgia,'Times New Roman',serif;background:#F8F3E9;color:#30251F;max-width:980px;margin:24px auto;padding:0 28px;line-height:1.5}
h1{font-size:26px;margin:0}h2{font-size:17px;color:#B96D50;border-bottom:1px solid #DCCAB0;padding-bottom:3px;margin-top:26px}
.meta{font-family:monospace;font-size:12px;color:#433A32}.draft{display:inline-block;border:2px solid #B96D50;color:#B96D50;
padding:2px 10px;font-weight:bold;letter-spacing:2px;font-family:monospace;margin-bottom:8px}table{width:100%;border-collapse:collapse;
font-size:12px;margin:6px 0}td,th{border:1px solid #DCCAB0;padding:4px 6px;vertical-align:top;text-align:left}th{background:#EFE5D3}
.ev{font-family:monospace;font-size:11px;color:#A86F45}.note{font-size:12px;background:#EFE5D3;border-left:3px solid #C69A55;padding:8px 10px}
.small{font-size:11px;color:#5a4d42}@media print{body{background:#fff;margin:0}.noprint{display:none}}"""


def _ev(ids):
    return " ".join(f'<span class="ev">{E(i)}</span>' for i in (ids or []) if i)


def render_html(R: dict) -> str:
    L = lambda t: E(language.label(t, R["lang"]))  # noqa: E731
    o = R["overview"]
    h = [f"<!doctype html><html lang='{R['lang']}'><head><meta charset='utf-8'><title>{E(R['caseId'])} — draft report</title>"
         f"<style>{CSS}</style></head><body>",
         f"<div class='draft'>{L('DRAFT')}</div><h1>{L('Draft Case Investigation Report')}: {E(R['caseId'])}</h1>",
         f"<div class='meta'>{E(o['title'] or '')}<br>{E(o['fir'] or '')} · {E(o['station'] or '')}, {E(o['district'] or '')} · "
         f"{E(o['agency'] or '')} · {E(o['offence'] or '')}<br>Incident: {E(o['incident'])} at {E(o['incidentPlace'] or '')} · "
         f"Registered: {E(o['registered'])} · IO: {E(o['io'] or '')}<br>Generated {E(R['generatedAt'])} · data hash "
         f"{E(R['dataHash'][:16])}</div>",
         f"<p class='noprint small'><a href='#' onclick='window.print();return false'>Print / save as PDF</a></p>",
         f"<h2>1. {L('Brief facts of the case')}</h2>",
         (f"<p class='note'>{E(R['translationNote'])}</p>" if R.get("translationNote") else ""),
         f"<p>{E(R['briefFacts'])}</p>",
         (f"<details class='small'><summary>English (verified)</summary><p>{E(R['briefFactsEnglish'])}</p></details>"
          if R["lang"] != "en" else ""),
         f"<h2>2. {L('Persons recorded')}</h2><table><tr><th>ID</th><th>Name</th><th>Recorded role</th><th>Source</th><th>Evidence</th></tr>"]
    h += [f"<tr><td>{E(p['personId'])}</td><td>{E(p['name'] or '')}</td><td>{E(p['recordedRole'].replace('_', ' ').lower())}</td>"
          f"<td>{E(p['roleSource'])}</td><td>{_ev(p['evidenceIds'][:3])}</td></tr>" for p in R["people"]]
    h.append(f"</table><p class='small'>Recorded roles are as written in police records; they are not findings of guilt.</p>"
             f"<h2>3. {L('Chronology')}</h2><table><tr><th>Time</th><th>Event</th><th>Evidence</th></tr>")
    h += [f"<tr><td>{E(c['timestamp'])}</td><td>{E(c['event'])}</td><td>{_ev(c['evidenceIds'][:3])}</td></tr>" for c in R["chronology"]]
    h.append(f"</table><h2>4. {L('Evidence collected')}</h2><p>Records by source: " +
             ", ".join(f"{E(k)}: {v}" for k, v in R["recordCounts"].items()) +
             "</p><table><tr><th>Exhibit</th><th>Type</th><th>Time</th><th>Description</th><th>Reliability</th><th>SHA-256 (ingestion)</th><th>Ledger</th></tr>")
    h += [f"<tr><td class='ev'>{E(x['evidenceId'])}</td><td>{E(x['type'])}</td><td>{E(x['time'])}</td><td>{E((x['description'] or '')[:160])}</td>"
          f"<td>{E(x['reliability'] or '')}</td><td class='ev'>{E(x['sha256'][:16])}…</td><td>#{E(x['ledgerBlock'])}</td></tr>" for x in R["exhibits"]]
    F = R["findings"]
    h.append(f"</table><h2>5. {L('Analytical findings')}</h2><p class='small'>Investigative indicators requiring verification — not findings of guilt.</p><ul>")
    h += [f"<li>Flagged transaction {_ev([f['evidenceId']])} ₹{f['amount']:,.0f} ({E(', '.join(f['methods']))}): {E(f['reasons'][0])}"
          + (f" <i>Alternative: {E(f['alternativeExplanation'])}</i>" if f.get("alternativeExplanation") else "") + "</li>"
          for f in F["financial"]["flagged"][:8]]
    h += [f"<li>Communication: {E(p['names'][0])} ↔ {E(p['names'][1])}, {p['total']} contacts ({E(p['first'])} – {E(p['last'])})</li>"
          for p in F["communication"]["pairs"][:5]]
    h += [f"<li>Location: {E(x['personId'])} recorded {x['distanceKm']} km from the incident, {x['minutesFromIncident']} min {_ev([x['evidenceId']])}</li>"
          for x in F["location"]["nearIncident"][:5]]
    h += [f"<li><b>Possibly exculpatory:</b> {E(x['personId'])} recorded at {E(x['location'])}, {x['distanceKm']} km away {_ev([x['evidenceId']])}</li>"
          for x in F["location"]["namedPersonsElsewhere"][:4]]
    h += [f"<li>Location inconsistency {E(t['personId'])}: {E(t['verdict'])} ({t['distanceKm']} km / {t['elapsedMinutes']} min) {_ev([t['first'], t['second']])}</li>"
          for t in F["travel"][:4]]
    h += [f"<li>{E(ob['text'])} {_ev(ob['evidenceIds'][:3])}</li>" for ob in F["observations"][:5]]
    h.append(f"</ul><h2>6. {L('Hypotheses tested')}</h2>")
    for hy in R["hypotheses"]:
        c = hy["confidence"]
        h.append(f"<p><b>{E(hy['hypothesis'])}</b><br>Supporting: " + "; ".join(f"{E(s['text'])} {_ev(s['evidenceIds'][:2])}" for s in hy["supporting"])
                 + "<br>Contradicting / exculpatory: " + "; ".join(f"{E(s['text'])} {_ev(s['evidenceIds'][:2])}" for s in hy["contradicting"])
                 + f"<br>Evidential balance {c['evidentialBalance']:+.2f} — {E(c['assessment'])}; completeness {round(c['completeness'] * 100)}% "
                   "(not a probability of guilt). Human review required.</p>")
        if hy.get("alternateHypotheses") is not None:
            h.append("<p><b>Alternate hypotheses — why this person may not have been involved:</b></p><ul>")
            h += [f"<li><b>{E(al['code'])} {E(al['title'])}</b> ({E(al['label'])}, {al['strength']:.2f}): {E(al['statement'])} "
                  + "; ".join(f"{E(x['text'])} {_ev(x['evidenceIds'][:2])}" for x in al["evidence"][:3])
                  + f"<br><span class='small'>Test that would settle it: {E(al['test'])}</span></li>" for al in hy["alternateHypotheses"]]
            h.append("</ul>" if hy["alternateHypotheses"] else "<li>No alternate explanation is supported by the records currently held.</li></ul>")
            h.append(f"<p><b>Line of inquiry vs alternates:</b> {E(hy['comparison']['verdict'])}</p>")
    h.append(f"<h2>7. {L('Pending investigation')}</h2><table><tr><th>Priority / value</th><th>Evidence to obtain or verify</th><th>Action</th><th>Status</th></tr>")
    h += [f"<tr><td>{E(r['priority'])} · {r['valueScore']}</td><td>{E(r['evidenceType'])}<br><span class='small'>{E(r['reason'])}</span></td>"
          f"<td>{E(r['verificationAction'])}</td><td>{E(r['status'])}</td></tr>" for r in R["pending"]]
    h.append(f"</table><h2>8. {L('Prior records (context only)')}</h2>")
    h.append("<ul>" + "".join(f"<li>{E(p['personId'])}: {E(p['record']['offence'])} ({E(p['record']['sections'])}), {E(p['record']['firReference'])}, "
                              f"{E(p['record']['disposition'])} — {E(p['band'])} link, {E(p['status'])} {_ev([p['record']['evidenceId']])}</li>"
                              for p in R["priorRecords"]) + "</ul>" if R["priorRecords"] else "<p>No prior record linked to persons in this case.</p>")
    h.append("<p class='small'>Prior records are context only; they are not evidence of the present allegation and were not used in any score.</p>")
    h.append(f"<h2>9. {L('Uncertainties and limitations')}</h2><ul>" + "".join(f"<li>{E(u)}</li>" for u in R["uncertainties"][:10])
             + "".join(f"<li>{E(m.get('personId') or '')} {E(m['gap'])}</li>" for m in R["missing"]) + "</ul>")
    I = R["integrity"]
    h.append(f"<h2>10. {L('Evidence integrity')}</h2><p>Evidence ledger chain: <b>{'VALID' if I['chainValid'] else 'INVALID'}</b> "
             f"({I['blocks']} blocks). Source batches for this case: " +
             "; ".join(f"{E(a['file'])} — Merkle root {E(a['merkleRoot'][:16])}…, {a['validSignatures']}/4 agency signatures" for a in I["anchors"])
             + ". Any exhibit can be re-verified in KRONOS (integrity check / Merkle proof). This shows the records are unchanged since "
               "ingestion; it does not establish authenticity or lawful collection.</p>")
    h.append("<p class='note'>DRAFT prepared by KRONOS from the records cited above, for review, correction and signature by the "
             "Investigating Officer. It is not a final report under BNSS s.193. Analytical findings are investigative indicators.</p>"
             "</body></html>")
    return "".join(h)


def render_diary_html(D: dict, lang: str = "en") -> str:
    L = lambda t: E(language.label(t, lang))  # noqa: E731
    h = [f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>{E(D['caseId'])} — case diary</title><style>{CSS}</style></head><body>",
         f"<div class='draft'>{L('DRAFT')}</div><h1>{L('Case Diary (Draft)')}: {E(D['caseId'])}</h1>",
         f"<div class='meta'>{E(D['firNumber'] or '')} · {E(D['policeStation'] or '')} · IO: {E(D['investigatingOfficer'] or '')} · generated "
         f"{E(D['generatedAt'])}</div><p class='noprint small'><a href='#' onclick='window.print();return false'>Print / save as PDF</a></p>"]
    texts = [it["text"] for e in D["entries"] for s in e["sections"] for it in s["items"]]
    tr, n = (language.translate_lines(texts, lang) if lang != "en" else (texts, len(texts)))
    if lang != "en":
        h.append(f"<p class='note'>{E(language.banner(lang))} {n} of {len(texts)} lines translated.</p>")
    k = 0
    for e in D["entries"]:
        h.append(f"<h2>{L('Day')} {e['day']} — {datetime.fromisoformat(e['date']):%d %b %Y}</h2>")
        for s in e["sections"]:
            h.append(f"<p><b>{L(s['section'])}</b></p><ul>")
            for it in s["items"]:
                h.append(f"<li>{E(it['time'])} {E(tr[k])} {_ev(it['refs'])}</li>"); k += 1
            h.append("</ul>")
    h.append(f"<p class='note'>{E(D['note'])}</p></body></html>")
    return "".join(h)


def diary(case_id: str) -> dict:
    return diary_mod.build(case_id)
