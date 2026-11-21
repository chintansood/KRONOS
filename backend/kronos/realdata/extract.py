"""Rule-based extraction of FIR particulars from High Court criminal-petition orders (bail / quashing).

Orders of the Punjab & Haryana High Court state the FIR in a few recurring forms, e.g.
  "... regular bail in case FIR No.395 dated 15.12.2022 under Sections 22/61/85 of NDPS Act registered at Police
   Station Dera Bassi, District SAS Nagar."
  "FIR No. Dated Police Station Sections  63 19.03.2010 DLF-II, Gurugram, District Gurugram 120-B, 201, 420 IPC"
Everything extracted keeps the character span it came from, so each field can be checked against the source text.
Fields that cannot be found are left empty — never guessed.
"""
from __future__ import annotations

import re
from datetime import date

ACTS = [(r"\bN\.?D\.?P\.?S\.?\b|Narcotic Drugs", "NDPS Act"), (r"Bharatiya Nyaya Sanhita|\bBNS\b", "BNS"),
        (r"Indian Penal Code|\bI\.?P\.?C\b", "IPC"), (r"Information Technology Act|\bI\.?T\.? Act", "IT Act"),
        (r"Arms Act", "Arms Act"), (r"Excise Act", "Excise Act"), (r"Immigration Act|Emigration Act", "Immigration/Emigration Act"),
        (r"Prevention of Corruption", "PC Act"), (r"Money Laundering|PMLA", "PMLA"), (r"Electricity Act", "Electricity Act"),
        (r"Disaster Management Act", "Disaster Management Act"), (r"Gambling Act", "Public Gambling Act"),
        (r"Mines and Minerals|MMDR", "Mines and Minerals Act"), (r"Motor Vehicles Act", "Motor Vehicles Act"),
        (r"Aircraft Act|Air Craft Act", "Aircraft Act"), (r"Explosive", "Explosive Substances Act"),
        (r"Scheduled Castes|SC/ST|Atrocities", "SC/ST (PoA) Act"), (r"POCSO|Protection of Children from Sexual", "POCSO Act"),
        (r"Juvenile Justice", "JJ Act"), (r"Dowry Prohibition", "Dowry Prohibition Act"), (r"Unlawful Activities|UAPA", "UAPA")]
ADDED_RX = r"\((?:[^()]|\([^()]*\))*?(?:added|later|deleted|substituted)(?:[^()]|\([^()]*\))*\)"
SEC_TOKEN = re.compile(r"\b\d{1,3}(?!\d)(?:\s?\(\d{1,2}\))*(?:\s?\([a-zA-Z]{1,3}\))?(?:-?[A-Z]{1,2}\b|\s?-\s?[A-Z]{1,2}\b)?(?:\(\d{1,2}\))?")
DATE = r"(\d{1,2})\s?[./-]\s?(\d{1,2})\s?[./-]\s?(\d{2,4})"


def iso(d: str | None) -> str | None:
    if not d:
        return None
    m = re.match(DATE, d.strip())
    if not m:
        return None
    dd, mm, yy = (int(x) for x in m.groups())
    yy = yy + 2000 if yy < 100 else yy
    try:
        return date(yy, mm, dd).isoformat()
    except ValueError:
        return None


def norm(t: str) -> str:
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\bCRM-M-\d+-\d{4}\b(?:\s*\(O&M\))?(?:\s*-?\s*\d{1,2}\s*-)?", " ", t)      # running page headers
    t = re.sub(r"[A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,4}\s+\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s+I attest to the accuracy and "
               r"(?:authenticity|integrity) of this document(?:\s+[A-Z][\w&.]*(?:\s+[\w&.]+){0,8}?\s+at\s+Chandigarh)?(?:\s+\d{1,2}\b)?",
               " ", t)                                                                       # digital-signature stamps
    t = re.sub(r"(?<=\w)- (?=[a-z])", "", t)                 # re-join words hyphenated across lines
    return t.strip()


def acts_in(s: str) -> list[str]:
    return list(dict.fromkeys(name for rx, name in ACTS if re.search(rx, s, re.I)))


def sections_in(span: str) -> list[str]:
    span = re.sub(ADDED_RX, " ", span, flags=re.I)                                                    # keep the base list
    span = re.sub(r"\bAct No\.?\s*\d+\s*/\s*\d{4}", " ", span, flags=re.I)
    span = re.sub(r"\b(1[89]|20)\d{2}\b", " ", span)                                                  # act years (IPC 1860 …)
    out = []
    for m in SEC_TOKEN.finditer(span):
        tok = re.sub(r"\s", "", m.group(0))
        if tok not in out and not re.fullmatch(r"0\d*", tok):
            out.append(tok)
    if len(out) >= 3:                       # bare single digits in long lists are page numbers / broken tokens
        out = [x for x in out if not re.fullmatch(r"\d", x)]
    return out[:25]


DISTRICTS = ["Amritsar Rural", "Amritsar", "Barnala", "Bathinda", "Faridkot", "Fatehgarh Sahib", "Fazilka", "Ferozepur", "Gurdaspur",
             "Hoshiarpur", "Jalandhar Rural", "Jalandhar", "Kapurthala", "Ludhiana Rural", "Ludhiana", "Malerkotla", "Mansa", "Moga",
             "Pathankot", "Patiala", "Rupnagar", "Ropar", "SAS Nagar", "Mohali", "SBS Nagar", "Nawanshahr", "Sangrur",
             "Sri Muktsar Sahib", "Muktsar", "Tarn Taran", "Batala", "Khanna", "Jagraon", "Ambala", "Bhiwani", "Charkhi Dadri",
             "Faridabad", "Fatehabad", "Gurugram", "Gurgaon", "Hisar", "Hansi", "Jhajjar", "Jind", "Kaithal", "Karnal", "Kurukshetra",
             "Mahendragarh", "Narnaul", "Nuh", "Mewat", "Palwal", "Panchkula", "Panipat", "Rewari", "Rohtak", "Sirsa", "Sonipat",
             "Yamunanagar", "Dabwali", "Chandigarh"]
STATE_OF = {d: "Haryana" for d in ["Ambala", "Bhiwani", "Charkhi Dadri", "Faridabad", "Fatehabad", "Gurugram", "Gurgaon", "Hisar", "Hansi",
                                   "Jhajjar", "Jind", "Kaithal", "Karnal", "Kurukshetra", "Mahendragarh", "Narnaul", "Nuh", "Mewat", "Palwal",
                                   "Panchkula", "Panipat", "Rewari", "Rohtak", "Sirsa", "Sonipat", "Yamunanagar", "Dabwali"]}
STATE_OF["Chandigarh"] = "Chandigarh (UT)"


_DSET = set(DISTRICTS)


def district_in(s: str) -> str | None:
    s2 = re.sub(r"\b([A-Z][a-z]{0,4}) ([a-z]{1,5})\b",                 # "Ma nsa" → "Mansa" (PDF spacing), known names only
                lambda m: m.group(1) + m.group(2) if m.group(1) + m.group(2) in _DSET else m.group(0), s or "")
    for d in DISTRICTS:
        if re.search(rf"\b{re.escape(d)}\b", s2):
            return d
    return None


PS_STOP = r"(?=\s*,|\s+District|\s+Distt|\s+Police Commissionerate|\s+Commissionerate|\s*\(|\s+and\b|\s+u/s|\s+under\b|\.\s|\s+in\b|\s+registered|$)"


def fir_fields(t: str) -> dict:
    """FIR number/date/sections/police station/district from prose or the tabular header used by some benches."""
    out = {"firNo": None, "firYear": None, "firDate": None, "sections": [], "acts": [], "policeStation": None,
           "district": None, "firSpan": None, "format": None}
    # tabular form
    m = re.search(r"FIR No\.?\s+Date[d]?\s+(Police Station\s+Sections?(?:\(s\))?|Sections?(?:\(s\))?\s+Police Station(?:\s+District)?)\s+"
                  r"(?:[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,3}\s+)?"
                  r"(\d{1,4})\s+" + DATE + r"\s+(.{8,320}?)(?=\s+\d\s?\.\s+[A-Z]|\s+2\s?\.\s|\s+1\s?\.\s|$)", t)
    if m:
        order, no, rest = m.group(1), m.group(2), m.group(6)
        added = sections_in(" ".join(x[1:-1] for x in re.findall(ADDED_RX, rest, re.I)))
        rest = re.sub(ADDED_RX, " ", rest, flags=re.I)
        d = iso(f"{m.group(3)}.{m.group(4)}.{m.group(5)}")
        acts = acts_in(rest)
        act_m = re.search(r"\b(IPC|BNS|NDPS Act|Arms Act|I\.P\.C\.?|of (?:the )?(?:NDPS|IPC|BNS)[^,]{0,40}?(?:\d{4})?)\b(?:\s*\([^)]*\))?", rest)
        if order.startswith("Police"):
            first_sec = re.search(r"(?<!No\.)(?<!No\. )(?<!No)(?<!-)\b\d{1,3}(?:\(\d+\))?(?:-[A-Z])?(?:\(\d+\))?\s*(?:,|/|and|of|\s+r/w|\s+(?:IPC|BNS))", rest)
            ps_part = rest[: first_sec.start()] if first_sec else rest
            sec_part = rest[first_sec.start():] if first_sec else ""
        else:
            ends = [mm.end() for rx, _ in ACTS for mm in re.finditer(rx + r"(?:[^,]{0,25}?\bAct\b)?", rest, re.I)]
            cut = max(ends) if ends else (act_m.end() if act_m else len(rest) // 2)
            tail = re.match(r"\s*,?\s*(?:(?:19|20)\d{2})?\s*(?:\([^)]*\))?", rest[cut:])
            cut += tail.end() if tail else 0
            sec_part, ps_part = rest[:cut], rest[cut:]
        ps = re.sub(r"^(?:Police Station|P\.S\.|PS)\s*", "", ps_part.strip(" ,.-")).strip()
        dd = district_in(ps)
        out.update(firNo=no.lstrip("0") or no, firDate=d, firYear=int(d[:4]) if d else None, sections=sections_in(sec_part),
                   acts=acts, district=dd, firSpan=m.group(0)[:400], format="table", sectionsAddedLater=added)
        ps = re.split(r",\s*District|\s+District", ps)[0].strip(" ,")
        ps = ps.split(",")[0].strip() if ps else None
        if ps and dd and ps.endswith(" " + dd) and re.search(r"\d", ps[: -len(dd)]):
            ps = ps[: -len(dd) - 1].strip()
        out["policeStation"] = ps or None
        if out["sections"] and out["policeStation"]:
            return out
    # prose form
    for m in re.finditer(r"FIR\s*No\.?\s*[:\-]?\s*(\d{1,4})(?:\s*(?:/|of)\s*((?:19|20)\d{2}))?", t):
        win = t[m.start(): m.start() + 600]
        d = re.search(r"d\s?ated\s*:?\s*" + DATE, win)
        sec = re.search(r"(?:under|u/s|for the offences? punishable under)\s+(?:Sections?|Ss?\.)?\s*(.{2,260}?)"
                        r"(?=\s*,?\s*(?:registered|at Police Station|Police Station|P\.S\.|(?<![A-Za-z])PS\s)|\s*\(Annexure|\.\s+[A-Z0-9])", win)
        ps = re.search(r"(?:Police Station|P\.S\.|\bPS)\s*[:\-]?\s*((?!District\b)[A-Z][A-Za-z0-9.\-]*(?:\s+(?!District\b|Distt\b|Police\b)[A-Z0-9][A-Za-z0-9.\-]*){0,4})" + PS_STOP, win)
        dist = re.search(r"(?:District|Distt\.?)\s+(?:Police Commissionerate\s+)?([A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,2})"
                         r"(?=\s*[,.;(]|\s+(?:Punjab|Haryana|and|under|registered|for|\()|$)", win) or \
            re.search(r"Police Commissionerate,?\s+([A-Z][a-z]+)", win)
        if not (sec and ps and d):
            continue
        fd = iso(f"{d.group(1)}.{d.group(2)}.{d.group(3)}") if d else None
        yr = int(m.group(2)) if m.group(2) else (int(fd[:4]) if fd else None)
        span = win[: (dist.end() if dist and dist.end() > ps.end() else ps.end())]
        psn = re.sub(r"\.\s*\d{1,2}$", "", ps.group(1).strip(" .,")).strip(" .,")      # "Sardulgarh. 2" (paragraph no.)
        dd = district_in(dist.group(1)) if dist else None
        dd = dd or district_in(win[ps.start(): ps.end() + 80])
        if dd and psn.endswith(" " + dd) and re.search(r"\d", psn[: -len(dd)]):     # "Division No.5 Ludhiana"
            psn = psn[: -len(dd) - 1].strip()
        added = sections_in(" ".join(x[1:-1] for x in re.findall(ADDED_RX, sec.group(1), re.I)))
        out["sectionsAddedLater"] = added
        out.update(firNo=m.group(1).lstrip("0") or m.group(1), firYear=yr, firDate=fd, sections=sections_in(sec.group(1)),
                   acts=acts_in(sec.group(1)), policeStation=psn, district=dd or (dist.group(1).strip(" .,") if dist else None),
                   firSpan=span, format="prose")
        if out["sections"]:
            return out
    return out


CATEGORY = [(None, r"^(302|307|103(\(\d\))?|109(\(\d\))?)$", "Murder / Attempt to Murder"),
            ("NDPS Act", None, "Narcotics (NDPS Act)"),
            (None, r"^(392|394|395|397|399|309(\(\d\))?|310(\(\d\))?)$", "Robbery & Dacoity"),
            ("IT Act", None, "Cyber Fraud (IT Act)"),
            (None, r"^(384|386|387|389|308(\(\d\))?)$", "Extortion & Criminal Intimidation"),
            (None, r"^(419|420|406|409|467|468|471|318(\(\d\))?|319(\(\d\))?|316(\(\d\))?|336(\(\d\))?|338|340(\(\d\))?)$", "Cheating, Fraud & Forgery"),
            (None, r"^(379|379-[AB]|380|411|457|454|303(\(\d\))?|305|317(\(\d\))?|331(\(\d\))?)$", "Theft & Burglary"),
            ("Arms Act", None, "Arms Act"), ("Excise Act", None, "Excise (illicit liquor)"),
            ("Immigration/Emigration Act", None, "Immigration Fraud"), ("PC Act", None, "Corruption"),
            ("Electricity Act", None, "Electricity Theft"),
            (None, r"^(323|324|325|326|341|342|506|148|149|115(\(\d\))?|117(\(\d\))?|118(\(\d\))?|126(\(\d\))?|190|191(\(\d\))?|351(\(\d\))?)$", "Hurt, Rioting & Intimidation")]


def category(sections: list[str], acts: list[str]) -> str:
    base = [re.sub(r"\(.*$", "", s) for s in sections] + sections
    for act, rx, name in CATEGORY:
        if act and act in acts:
            return name
        if rx and any(re.match(rx, s) for s in base):
            return name
    return "Other Criminal Matter"


EXCLUDE = [(r"\bPOCSO\b|Protection of Children from Sexual", "child sexual offence (POCSO)"),
           (r"\b376[A-E]?\b|\b354[A-D]?\b|\b509\b|\brape\b|sexual|outrag(e|ing) (the )?modesty|prosecutrix", "sexual offence / modesty of a woman"),
           (r"Juvenile Justice|child in conflict|\bJJ Act", "juvenile matter"),
           (r"Scheduled Castes|SC/ST|Atrocities", "SC/ST Act (caste-related)"),
           (r"\b498-?A\b|\b304-?B\b|\bdowry\b|matrimonial|\b85 of (the )?B(NS|haratiya)", "matrimonial / dowry matter")]


def exclusion(text: str, fir: dict) -> str | None:
    """First reason a record is excluded (victims' identity protection, caste data, family matters), or None."""
    r = exclusions(text, fir)
    return r[0] if r else None


def exclusions(text: str, fir: dict) -> list[str]:
    sec = " ".join(fir.get("sections") or [])
    bns = "BNS" in (fir.get("acts") or [])
    out = []
    if bns and re.search(r"\b(6[3-9]|7[0-9])\b", sec):          # BNS 63-79: sexual offences
        out.append("sexual offence (BNS 63-79)")
    if bns and re.search(r"\b(87|96|137|139)\b", sec):          # BNS kidnapping/abduction (minors, women)
        out.append("kidnapping / abduction (BNS 87/96/137/139)")
    if not bns and re.search(r"\b(363|366|366-A|366-B|372|373)\b", sec):
        out.append("kidnapping / abduction of minors or women (IPC 363/366)")
    if bns and re.search(r"\b(80|85|86)\b", sec):
        out.append("matrimonial / dowry matter (BNS 80/85/86)")
    out += [why for rx, why in EXCLUDE if re.search(rx, text, re.I)]
    return out


def petition_type(t: str) -> str:
    tl = t[:3000].lower()
    for k, v in (("anticipatory bail", "ANTICIPATORY_BAIL"), ("cancellation of bail", "BAIL_CANCELLATION"),
                 ("regular bail", "REGULAR_BAIL"), ("bail pending trial", "REGULAR_BAIL"), ("suspension of sentence", "SUSPENSION_OF_SENTENCE"),
                 ("quashing", "QUASHING"), ("quash", "QUASHING"), ("grant of bail", "REGULAR_BAIL")):
        if k in tl:
            return v
    return "OTHER"


FACT_START = re.compile(r"(?:brief facts of the case (?:are|is) (?:that|as under)|facts of the case (?:are|is) (?:that|as under)|"
                        r"(?:As|as) per the (?:allegations|prosecution case|prosecution story|case of the prosecution|FIR)[, ]|"
                        r"(?:Succinctly|Briefly), the facts|case set up in the FIR|Prosecution story|prosecution version|"
                        r"which reads as (?:follows|under)\s*:?|the allegations (?:are|against the petitioner are) that)", re.I)
FACT_STOP = re.compile(r"\s(?:\d{1,2}\s?\.\s+)?(?:Learned counsel|learned counsel for the petitioner|Heard|I have heard|"
                       r"On the other hand|Per contra|In view of|Notice of motion|Learned State counsel|The learned State counsel|"
                       r"It is (?:contended|submitted)|Counsel for the petitioner)", re.I)


def facts(t: str, max_chars: int = 1400) -> str | None:
    m = FACT_START.search(t)
    if not m:
        return None
    body = t[m.end(): m.end() + 4000].lstrip(" :-–—“\"'‘")
    stop = FACT_STOP.search(body, 120)
    body = body[: stop.start()] if stop else body
    body = re.sub(r"CRM-M-\d+-\d{4}(?:\s*\(O&M\))?\s*-?\d{0,2}-?|-\d-\s", " ", body)   # running page headers
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) > max_chars:
        cut = body.rfind(". ", 0, max_chars)
        body = body[: cut + 1] if cut > 200 else body[:max_chars]
    return body if len(body) > 120 else None


def antecedents(t: str) -> dict:
    tl = t.lower()
    if re.search(r"no (known )?(criminal )?antecedents|clean antecedents|not involved in any other (criminal )?case|first[- ]time offender|"
                 r"no other (fir|case) has been registered", tl):
        return {"declared": "NONE", "items": []}
    m = re.search(r"(criminal antecedents|involved in the following|other cases? registered against)", t, re.I)
    if not m:
        return {"declared": "NOT_STATED", "items": []}
    win = t[m.end(): m.end() + 1500]
    items = []
    for r in re.finditer(r"(?:^|\s)(\d{1,2})\s?\.\s+(\d{1,4})(?:/((?:19|20)\d{2}))?\s+(" + DATE[1:-1] + r"|-)?\s*([\d ,/()\-A-Za-z.]{3,90}?(?:IPC|BNS|NDPS Act|Act))"
                         r"\s+([A-Z][A-Za-z .\-]{2,40}?)(?=\s+\d{1,2}\s?\.\s|\s+\d\.|$)", win):
        items.append({"serial": int(r.group(1)), "firNo": r.group(2), "year": r.group(3), "sections": r.group(5).strip(),
                      "policeStation": r.group(6).strip()})
        if len(items) >= 12:
            break
    return {"declared": "LISTED" if items else "MENTIONED", "items": items}


EVIDENCE = [("CDR / call records", r"\bCDRs?\b|call detail|call records|tower location|cell tower"),
            ("CCTV footage", r"\bCCTV\b"), ("Bank / UPI records", r"bank statement|bank account|\bUPI\b|transferred|transaction|NEFT|RTGS|IMPS"),
            ("Chats / social media", r"WhatsApp|Telegram|Instagram|Facebook|chats?\b"), ("Mobile phone recovered", r"mobile phones? (was |were )?recovered|recovery of (a |one |two |\d )?mobile"),
            ("Forensic (FSL / chemical examiner)", r"\bFSL\b|chemical examiner|forensic"), ("Recovery / seizure memo", r"recovery memo|seizure memo|was recovered|were recovered|recovery of"),
            ("Medical (MLR / post-mortem)", r"\bMLR\b|medico-?legal|post-?mortem|injur"), ("Disclosure statement", r"disclosure statement")]


def evidence_mentions(t: str) -> list[str]:
    return [name for name, rx in EVIDENCE if re.search(rx, t, re.I)]


def amounts(t: str) -> list[float]:
    out = []
    for m in re.finditer(r"(?:Rs\.?|₹|INR)\s?([\d,]+(?:\.\d+)?)\s*(?:/-)?\s*(lakhs?|lacs?|crores?)?", t, re.I):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        v *= 1e5 if unit.startswith(("lakh", "lac")) else 1e7 if unit.startswith("crore") else 1
        if v >= 100:
            out.append(round(v, 2))
    return out[:10]


def recoveries(t: str) -> list[str]:
    out = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(kgs?|kilograms?|grams?|gms?|gm|g)\.?\s+(?:of\s+)?(heroin|heroine|opium|poppy husk|poppy straw|charas|ganja|"
                         r"smack|cocaine|methamphetamine|alprazolam|tramadol|intoxicant powder|ice)", t, re.I):
        out.append(f"{m.group(1)} {m.group(2).lower()} {m.group(3).lower()}")
    for m in re.finditer(r"(\d[\d,]*)\s+(?:intoxicant\s+)?(tablets|capsules|injections|bottles of [a-z ]{3,20}|strips)", t, re.I):
        out.append(f"{m.group(1)} {m.group(2).lower()}")
    return list(dict.fromkeys(out))[:6]


def custody_since(t: str) -> str | None:
    m = re.search(r"in custody since\s+" + DATE, t, re.I) or re.search(r"arrested on\s+" + DATE, t, re.I)
    return iso(".".join(m.groups()[-3:])) if m else None


def extract(text: str, meta: dict) -> dict:
    t = norm(text)
    fir = fir_fields(t)
    return {"fir": fir, "petitionType": petition_type(t), "facts": facts(t), "antecedents": antecedents(t),
            "evidenceMentioned": evidence_mentions(t), "amounts": amounts(t), "recoveries": recoveries(t),
            "custodySince": custody_since(t),
            "category": category(fir["sections"] + fir.get("sectionsAddedLater", []), fir["acts"]) if fir["sections"] else None,
            "excluded": exclusion(t, fir), "exclusionReasons": exclusions(t, fir), "disposal": meta.get("disposal_nature"), "text": t}
