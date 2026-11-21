"""Pseudonymisation of real court-order text before it enters KRONOS.

Real people must not be profiled by an investigation system on the strength of a public court order, and must never be
fuzzy-matched to synthetic records. So every natural person is replaced by a role label scoped to the case
("[Accused A1]", "[Complainant C1]", "[Person X2]"), and direct identifiers are masked (phone, vehicle registration,
Aadhaar-like and account numbers, addresses, villages). Courts, police stations, districts, statutes and dates stay —
they are what make the record a real, checkable case.

Layers: (1) names of the parties from the case title; (2) names in role contexts ("complainant X", "son of Y",
"namely Z", "@ alias"); (3) title-case sequences containing a known Indian given name or surname; (4) a residual scan
that masks any remaining lexicon name. The residual count is reported per record so leakage is measurable.
"""
from __future__ import annotations

import re

from ..synth.world import FATHER_FIRST, FEMALE_FIRST, MALE_FIRST, NICKNAMES, SURNAMES
from .extract import DISTRICTS

EXTRA_GIVEN = """Aman Amandeep Amarjit Amarjeet Amrik Angrej Anil Anoop Arshdeep Avtar Baljinder Baljit Balkar Balwant Balwinder Bhupinder
Bikramjit Bobby Charanjit Daljit Darshan Davinder Deepak Dharam Dilbagh Gagandeep Gurbachan Gurcharan Gurdeep Gurdev Gurjant Gurjeet
Gurmeet Gurmej Gurnam Gurpreet Gursewak Harbans Hardeep Harjinder Harjit Harkesh Harman Harmesh Harminder Harnek Harvinder Hasanpreet
Inderjit Iqbal Jagdeep Jagjit Jagroop Jagtar Jaskaran Jaspal Jaspreet Jaswant Jaswinder Jatinder Jitender Joginder Kamaljit Kamaljeet
Kashmir Kewal Kuldip Kuldeep Kulwant Kulwinder Lakhbir Lakhwinder Lovepreet Maninder Manjit Manjeet Manpreet Mohinder Mahinder Nachhattar
Naresh Navdeep Navjot Nirmal Palwinder Paramjit Pargat Parminder Pawan Prem Raghbir Rajbir Rajinder Rajwinder Ramesh Ranjit Ravinder
Rupinder Sakattar Sarabjit Satnam Satpal Shamsher Sohan Sucha Sukhdev Sukhjinder Sukhpreet Sukhwinder Surat Surjit Swaran Tarsem Varinder
Vijay Yadwinder Rajan Anjana Rohit Mohit Sumit Ajay Anuj Ankit Ashok Babloo Bablu Bittu Gopal Hans Jagdish Kishan Krishan Lachman Madan
Mukesh Pardeep Pradeep Rakesh Ramesh Sanjeev Satish Suresh Sushil Vinod Virender Yogesh Anas Imran Irfan Salim Shahid Wasim Akhtar Javed
Kamla Kanta Kiran Lajwanti Manjeet Nirmala Parveen Rajni Ranjit Santosh Savitri Sheela Shanti Surinder Usha Veena Jasdeep Tota Gora Sukhi
Goldi Sonu Monu Pinka Kala Bhola Lucky Happy Honey Raju Pappu Titu Tinku Rinku Goldy Dimpy Pinky Ravi Sunny Bunty Vicky""".split()
EXTRA_SUR = """Kumar Kumari Devi Rani Lal Chand Ram Dass Das Nath Pal Prakash Khan Ali Ahmed Mohammad Mohd Masih Bajwa Brar Cheema Chahal Dhaliwal
Dhillon Grewal Hundal Johal Kahlon Kang Khaira Khehra Mann Randhawa Saini Sekhon Sohi Toor Virk Walia Bhatti Bhullar Goyal Garg Jindal
Mittal Singla Goel Aggarwal Agarwal Kapoor Khanna Malhotra Chopra Sethi Bedi Ahuja Arora Sood Bhatia Chawla Dhawan Gulati Juneja Kalra
Kohli Luthra Madan Narang Taneja Tandon Yadav Jat Dahiya Malik Hooda Sangwan Rathee Phogat Punia Sheoran Tanwar Chauhan Rana Rawat
Thakur Negi Pandey Mishra Tiwari Dubey Shukla Tripathi Joshi Bhardwaj Vashisht Kaushik Gaba Dhariwal Rasik Safi""".split()
LEXICON = {w.lower() for w in (MALE_FIRST + FEMALE_FIRST + SURNAMES + EXTRA_GIVEN + EXTRA_SUR)} | \
    {w.lower() for f in FATHER_FIRST for w in f.split()} | {n.lower() for v in NICKNAMES.values() for n in v}
NOT_NAMES = {"state", "court", "police", "station", "district", "high", "punjab", "haryana", "chandigarh", "india", "act", "section",
             "sections", "sessions", "judge", "judicial", "magistrate", "learned", "counsel", "advocate", "petitioner", "respondent",
             "complainant", "accused", "investigating", "officer", "bank", "limited", "ltd", "pvt", "honble", "hon'ble", "justice",
             "government", "general", "additional", "deputy", "city", "sadar", "cantonment", "civil", "lines", "division", "model",
             "town", "nagar", "mandi", "sahib", "colony", "road", "chowk", "bazar", "market", "village", "tehsil", "block",
             "commissionerate", "annexure", "status", "report", "fir", "ndps", "ipc", "bns", "bnss", "crpc", "january", "february",
             "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "monday", "tuesday",
             "wednesday", "thursday", "friday", "saturday", "sunday", "gurudwara", "temple", "mosque", "church", "school", "hospital",
             "university", "college", "company", "services", "cards", "payment", "railway", "delhi", "airport", "border", "bsf", "stf"}
ROLE_OF = [(r"complainant|informant|statement of", "Complainant", "C"), (r"deceased|victim|injured", "Victim", "V"),
           (r"witness", "Witness", "W"), (r"co-?accused|accused|petitioner", "Accused", "A"),
           (r"\b(?:ASI|SI|HC|EHC|PHC|Inspector|Constable|DSP|SHO|Sub[- ]Inspector)\b", "Police official", "O"),
           (r"advocate|counsel|D\.?A\.?G|A\.?A\.?G|A\.?G\b", "Counsel", "L")]
CTX = re.compile(r"(?<![A-Za-z])((?i:complainant|informant|petitioners?|co-?accused|accused|deceased|victim|injured|witness|namely|one|statement of|"
                 r"whose name is|name is|named|"
                 r"son of|daughter of|wife of|husband of|widow of|brother of|father of|mother of|S/o|D/o|W/o|s/o|d/o|w/o|"
                 r"Sh\s?\.|Shri|Smt\s?\.|Mr\s?\.|Mrs\s?\.|Ms\s?\.|Dr\s?\.|Inspector|Constable|alias)|ASI|SI|HC|EHC|PHC|DSP|SHO|@)"
                 r"[\s\-–:,]*(?:namely\s+|late\s+|Late\s+|Sh\.\s*|Smt\.\s*)?((?:[A-Z][a-z]+)(?:\s+(?:[A-Z][a-z]+|@|alias)){0,4})")
TITLE_SEQ = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
IDENTIFIERS = [(re.compile(r"(?:\+91[-\s]?)?\b[6-9]\d{4}[-\s]?(?:\d{5}|[xX]{5})\b"), "[phone withheld]"),
               (re.compile(r"\b[A-Z]{2}[-\s]?\d{1,2}[-\s]?[A-Z]{0,3}[-\s]?\d{3,4}\b"), "[vehicle no. withheld]"),
               (re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"), "[ID no. withheld]"),
               (re.compile(r"\b\d{9,18}\b"), "[account/ID no. withheld]"),
               (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email withheld]"),
               (re.compile(r"\b(resident of|residents of|R/o|r/o|residing at)\s+(?:House No\.?\s*[\w/-]+,?\s*)?(?:[Vv]illage\s+)?[A-Z][\w.\- ]{1,40}?(?=,|\.|\s+(?:District|Tehsil|P\.S\.|Police|police|aged|and|who|had|has|was|were|is|are|along|alongwith|went|came)\b)"),
                r"\1 [address withheld]"),
               (re.compile(r"\b([Vv]illage|[Vv]ill\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"), r"\1 [withheld]")]


_DICT: set[str] | None = None
KEEP = {"ipc", "bns", "bnss", "ndps", "crpc", "fir", "ddr", "asi", "hc", "dsp", "sho", "sdm", "fsl", "mlr", "cctv", "cdr", "cdrs", "upi",
        "neft", "rtgs", "imps", "whatsapp", "telegram", "instagram", "facebook", "aadhaar", "imei", "gps", "dag", "aag", "addl", "punjab",
        "haryana", "chandigarh", "delhi", "india", "indian", "hindi", "punjabi", "bharatiya", "nyaya", "sanhita", "nagarik", "suraksha",
        "adhiniyam", "lok", "adalat", "sessions", "tehsildar", "naib", "lambardar", "sarpanch", "panchayat", "gurdwara", "gurudwara",
        "mohalla", "chowk", "bazar", "mandi", "nagar", "colony", "enclave", "vihar", "sector", "phase", "rupees", "lakh", "lakhs",
        "crore", "crores", "heroin", "opium", "charas", "ganja", "smack", "alprazolam", "tramadol", "poppy", "husk", "bsf", "stf",
        "antf", "sit", "cia", "cbi", "ed", "nri", "ltd", "pvt", "mohali", "gurugram", "gurgaon", "ludhiana", "amritsar", "jalandhar"} | \
       {d.lower() for d in DISTRICTS} | {w for d in DISTRICTS for w in d.lower().split()}


def english() -> set[str]:
    """System English word list minus Indian names, so 'Kaku' or 'Mamta' (absent) are masked and 'Police' is kept."""
    global _DICT
    if _DICT is None:
        try:
            _DICT = {w.strip().lower() for w in open("/usr/share/dict/words", encoding="utf-8", errors="ignore") if w.strip()}
        except OSError:
            _DICT = set()
        _DICT -= LEXICON
    return _DICT


def _is_name(seq: str, protected: set[str]) -> bool:
    toks = [t.strip(".").lower() for t in seq.split() if t not in ("@", "alias")]
    if not toks or seq in protected or any(t in NOT_NAMES for t in toks):
        return False
    return any(t in LEXICON for t in toks)


class Pseudonymizer:
    """One instance per case, so labels are consistent within a record and never shared across cases."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.map: dict[str, str] = {}
        self.count = {"A": 0, "C": 0, "V": 0, "W": 0, "O": 0, "L": 0, "X": 0}
        self.roles: dict[str, str] = {}
        self.withheld: dict[str, str] = {}      # safety-net masks: neutral, consistent within the record

    def label(self, name: str, role_hint: str = "") -> str:
        key = re.sub(r"\s+", " ", name.strip(" .,")).lower()
        if key in self.map:
            return self.map[key]
        role, prefix = "Person", "X"
        for rx, r, p in ROLE_OF:
            if re.search(rx, role_hint, re.I):
                role, prefix = r, p
                break
        self.count[prefix] += 1
        lab = f"[{role} {prefix}{self.count[prefix]}]" if prefix not in "L" else "[counsel]"
        self.map[key] = lab
        self.roles[lab] = role
        return lab

    def add_parties(self, title: str):
        """Petitioners named in the case title ('CRM-M/123/2025 of A AND B Vs STATE OF PUNJAB')."""
        m = re.search(r" of (.+?) Vs\.? ", title or "", re.I)
        if not m:
            return []
        raw = re.sub(r"\b(AND (ANR|ORS|OTHERS|ANOTHER)|ETC)\b\.?", "", m.group(1), flags=re.I)
        names = []
        for part in re.split(r"\s+AND\s+|,", raw):
            for nm in re.split(r"\s+(?:ALIAS|@)\s+", part.strip(), flags=re.I):
                nm = nm.strip(" .").title()
                if len(nm) >= 3:
                    names.append(nm)
                    self.label(nm, "petitioner")
        return names

    def apply(self, text: str, protected: set[str]) -> tuple[str, dict]:
        if not text:
            return text, {"names": 0, "identifiers": 0, "residual": 0}
        # protect police stations, districts and other non-personal strings from accidental masking
        prot = sorted({p for p in protected | set(DISTRICTS) if p}, key=len, reverse=True)
        ph = {}
        for i, p in enumerate(prot):
            tok = f"⟦P{i}⟧"
            if re.search(rf"\b{re.escape(p)}\b", text):
                text = re.sub(rf"\b{re.escape(p)}\b", tok, text)
                ph[tok] = p
        n_id = 0
        for rx, rep in IDENTIFIERS:
            text, k = rx.subn(rep, text)
            n_id += k
        # role-context names
        for m in CTX.finditer(text):
            seq = m.group(2)
            for nm in re.split(r"\s+(?:@|alias)\s+", seq):
                nm = nm.strip(" .")
                toks = nm.split()
                while toks and toks[-1].lower() in NOT_NAMES:
                    toks.pop()
                nm = " ".join(toks)
                ctx = m.group(1).lower()
                honorific = re.match(r"(sh|shri|smt|mr|mrs|ms|dr)\b", ctx) is not None      # "Ms. <name> …" — always a person
                if nm and (any(t.lower() in LEXICON for t in toks) or honorific or ctx in ("@", "alias", "namely", "whose name is", "name is", "named")) \
                        and not any(t.lower() in NOT_NAMES for t in toks):
                    hint = ctx + (" " + text[max(0, m.start() - 25): m.start()] if ctx in ("namely", "@", "alias") else "")
                    self.label(nm, hint)
        # title-case sequences with lexicon names
        for m in TITLE_SEQ.finditer(text):
            if _is_name(m.group(1), protected):
                self.label(m.group(1), "")
        # "X @ Y" / "X alias Y": one person, one label
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s*(?:@|alias)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text):
            a_, b_ = m.group(1).lower(), m.group(2).lower()
            if a_ in self.map and b_ in self.map and self.map[a_] != self.map[b_]:
                self.map[b_] = self.map[a_]
        n_names = 0
        for key in sorted(self.map, key=len, reverse=True):
            text, k = re.subn(rf"\b{re.escape(key)}\b", self.map[key], text, flags=re.I)
            n_names += k
        # single given names left over from replaced full names (e.g. "Jaskaran" after "Jaskaran Singh")
        for key, lab in list(self.map.items()):
            first = key.split()[0]
            if len(key.split()) > 1 and len(first) >= 4 and first in LEXICON and first not in ("singh", "kaur", "kumar", "devi"):
                text, k = re.subn(rf"\b{re.escape(first)}\b", lab, text, flags=re.I)
                n_names += k
        # safety net: any remaining capitalised word that is not an English word, legal/place vocabulary or a protected
        # string is treated as a possible name and masked (over-masks some village names — the safe failure)
        residual = 0
        eng = english()

        def res(m):
            nonlocal residual
            w = m.group(0)
            lw = w.lower()
            if lw in KEEP or lw in NOT_NAMES or (lw in eng and lw not in LEXICON):
                return w
            residual += 1
            if lw not in self.withheld:
                self.withheld[lw] = f"[Name W{len(self.withheld) + 1}]"
            return self.withheld[lw]
        text = re.sub(r"(?<![\[⟦A-Za-z])[A-Z][A-Za-z]{2,}\b(?![\]⟧])", res, text)
        text = re.sub(r"(\[(?:Accused|Complainant|Victim|Witness|Person|Police official) [A-Z]\d+\])(?:\s+\1)+", r"\1", text)
        text = re.sub(r"(\[Name W\d+\])(?:\s+\1)+", r"\1", text)
        for tok, p in ph.items():
            text = text.replace(tok, p)
        return text, {"names": n_names, "identifiers": n_id, "residual": residual, "labels": len(self.map)}
