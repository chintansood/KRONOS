"""Multilingual layer (English, Hindi, Gujarati, Punjabi) for the assistant and generated documents.

Queries in Indian languages are detected by script and translated to English for intent detection and
retrieval; answers are produced and checked in English (citations, grounding), then translated back.
Before translation every identifier, amount, date and number is replaced by a placeholder and restored
afterwards — the model never sees (and so cannot corrupt) evidence IDs, account numbers or amounts. If any
placeholder is lost, the translation is rejected and the verified English text is returned instead.
"""
from __future__ import annotations

import re

from . import ollama

LANGS = {"en": "English", "hi": "Hindi", "gu": "Gujarati", "pa": "Punjabi (Gurmukhi script)"}
SCRIPTS = {"hi": (0x0900, 0x097F), "gu": (0x0A80, 0x0AFF), "pa": (0x0A00, 0x0A7F)}
PROTECT = re.compile(r"(EVD-[A-Z]+\d+|CASE\d{3}|\bP\d{5}\b|NBE-[0-9A-F]{10}|IDC-P\d{5}-P\d{5}|HL-HIST\d+-P\d{5}|HIST\d{6}|"
                     r"[A-Z]{4}-\d{11}|\+91-\d{10}|IMEI-\d{15}|SIM-\d{16}|ORG-\d{3}|AGY-[A-Z]{2,3}|FIR/[A-Z0-9/]+|"
                     r"₹\s?[\d,]+(?:\.\d+)?|\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\b\d{1,2}:\d{2}\b|"
                     r"\b\d+(?:[.,]\d+)+\b|\b\d{3,}\b)")
PH = re.compile(r"⟦(\d+)⟧")


def detect(text: str) -> str:
    counts = {k: sum(1 for ch in text if lo <= ord(ch) <= hi) for k, (lo, hi) in SCRIPTS.items()}
    k, n = max(counts.items(), key=lambda x: x[1])
    return k if n >= 2 else "en"


def _mask(text: str, start: int = 0) -> tuple[str, list[str]]:
    vals: list[str] = []

    def sub(m):
        vals.append(m.group(0))
        return f"⟦{start + len(vals) - 1}⟧"
    return PROTECT.sub(sub, text), vals


def _unmask(text: str, vals: list[str]) -> tuple[str, bool]:
    found = set(int(i) for i in PH.findall(text))
    ok = found == set(range(len(vals)))
    return PH.sub(lambda m: vals[int(m.group(1))] if int(m.group(1)) < len(vals) else m.group(0), text), ok


def to_english(text: str) -> str:
    """Questions: plain translation works well; identifiers from the original are re-attached if dropped."""
    if detect(text) == "en":
        return text
    out = ollama.chat([{"role": "system", "content": "Translate the user's question into English. Output only the translation."},
                       {"role": "user", "content": text}], max_tokens=120, temperature=0)
    missing = [t for t in PROTECT.findall(text) if t not in out]
    return out + (" " + " ".join(missing) if missing else "")


QUALITY = {"hi": "good", "gu": "limited", "pa": "limited"}


def banner(lang: str) -> str:
    q = QUALITY.get(lang, "limited")
    return (f"[Machine translation to {LANGS[lang]} — quality {q}; identifiers, amounts and dates are protected and "
            "unchanged. The verified English answer is authoritative.]")


def translate(text: str, lang: str, max_tokens: int = 900) -> tuple[str, bool]:
    """Translate verified English text into `lang`, preserving every protected token. Returns (text, ok)."""
    if lang == "en" or not text.strip():
        return text, True
    masked, vals = _mask(text)
    out = ollama.chat([{"role": "system", "content": f"Translate the user's text into {LANGS[lang]}. Every token like ⟦0⟧, "
                                                       "⟦1⟧ … must appear in your output exactly once and unchanged. Keep "
                                                       "line breaks, bullet points and **bold** markers. Output only the translation."},
                       {"role": "user", "content": masked}], max_tokens=max_tokens, temperature=0)
    # every real number/date was masked, so any digit outside a placeholder was invented by the translator
    stray_digits = re.search(r"[0-9\u0966-\u096F\u0AE6-\u0AEF\u0A66-\u0A6F]", PH.sub("", out))
    restored, ok = _unmask(out, vals)
    return (restored, True) if ok and not stray_digits else (text, False)


STRAY = re.compile(r"[0-9\u0966-\u096F\u0AE6-\u0AEF\u0A66-\u0A6F]")
SYS_LINES = ("Translate each numbered line into {lang}. Keep the <n> line numbers. Every token like ⟦0⟧ must appear "
             "exactly once, unchanged, in the same line. Keep **bold** markers and bullets. Output only the numbered lines.")


def _accept(masked_out: str, ids: list[int]) -> bool:
    return sorted(int(i) for i in PH.findall(masked_out)) == sorted(ids) and not STRAY.search(PH.sub("", masked_out))


def translate_lines(lines: list[str], lang: str, batch: int = 6) -> tuple[list[str], int]:
    """Per-line validated translation: each line is accepted only if all its protected tokens survive and no
    digits were invented; failed lines are retried once and otherwise kept in English.
    Returns (lines, number_translated)."""
    if lang == "en":
        return lines, len(lines)
    out, done = list(lines), 0
    todo = [i for i, t in enumerate(lines) if t.strip() and re.search(r"[A-Za-z]", t)]
    for attempt in range(2):
        if attempt == 1 and len(todo) > 4:      # keep latency bounded: retry only a few failed lines
            break
        failed = []
        size = batch if attempt == 0 else 1
        for b in range(0, len(todo), size):
            idx = todo[b:b + size]
            masked, vals, ids = [], {}, {}
            n = 0
            for k, i in enumerate(idx):
                m, v = _mask(lines[i], n)
                ids[k] = list(range(n, n + len(v)))
                for j, val in enumerate(v):
                    vals[n + j] = val
                n += len(v)
                masked.append(f"<{k}> {m}")
            try:
                res = ollama.chat([{"role": "system", "content": SYS_LINES.format(lang=LANGS[lang])},
                                   {"role": "user", "content": "\n".join(masked)}], max_tokens=220 * len(idx),
                                  temperature=0 if attempt == 0 else 0.2)
            except ollama.LLMUnavailable:
                return out, done
            got = dict(re.findall(r"<(\d+)>\s*(.*)", res))
            for k, i in enumerate(idx):
                t = got.get(str(k), "")
                if t.strip() and _accept(t, ids[k]):
                    out[i] = PH.sub(lambda m: vals.get(int(m.group(1)), m.group(0)), t).strip()
                    done += 1
                else:
                    failed.append(i)
        todo = failed
        if not todo:
            break
    return out, done


# Static UI / document labels (no machine translation needed)
LABELS = {
    "hi": {"Draft Case Investigation Report": "मसौदा केस जाँच रिपोर्ट", "Case Diary (Draft)": "केस डायरी (मसौदा)",
           "Brief facts of the case": "मामले के संक्षिप्त तथ्य", "Persons recorded": "दर्ज व्यक्ति", "Chronology": "घटनाक्रम",
           "Evidence collected": "एकत्रित साक्ष्य", "Analytical findings": "विश्लेषणात्मक निष्कर्ष",
           "Hypotheses tested": "परखी गई परिकल्पनाएँ", "Pending investigation": "लंबित जाँच",
           "Prior records (context only)": "पूर्व रिकॉर्ड (केवल संदर्भ)", "Uncertainties and limitations": "अनिश्चितताएँ और सीमाएँ",
           "Evidence integrity": "साक्ष्य की अखंडता", "Information received": "प्राप्त सूचना", "Statements recorded": "दर्ज बयान",
           "Steps taken / evidence collected": "उठाए गए कदम / एकत्रित साक्ष्य", "Circumstances ascertained": "ज्ञात परिस्थितियाँ",
           "Places visited": "देखे गए स्थान", "Investigator entries": "जाँच अधिकारी की प्रविष्टियाँ", "Next steps": "अगले कदम",
           "DRAFT": "मसौदा", "Day": "दिन"},
    "gu": {"Draft Case Investigation Report": "મુસદ્દો કેસ તપાસ અહેવાલ", "Case Diary (Draft)": "કેસ ડાયરી (મુસદ્દો)",
           "Brief facts of the case": "કેસની સંક્ષિપ્ત હકીકતો", "Persons recorded": "નોંધાયેલ વ્યક્તિઓ", "Chronology": "ઘટનાક્રમ",
           "Evidence collected": "એકત્રિત પુરાવા", "Analytical findings": "વિશ્લેષણાત્મક તારણો",
           "Hypotheses tested": "ચકાસાયેલ પૂર્વધારણાઓ", "Pending investigation": "બાકી તપાસ",
           "Prior records (context only)": "અગાઉના રેકોર્ડ (માત્ર સંદર્ભ)", "Uncertainties and limitations": "અનિશ્ચિતતાઓ અને મર્યાદાઓ",
           "Evidence integrity": "પુરાવાની અખંડિતતા", "Information received": "મળેલી માહિતી", "Statements recorded": "નોંધાયેલા નિવેદનો",
           "Steps taken / evidence collected": "લેવાયેલા પગલાં / એકત્રિત પુરાવા", "Circumstances ascertained": "જાણવા મળેલ સંજોગો",
           "Places visited": "મુલાકાત લીધેલ સ્થળો", "Investigator entries": "તપાસ અધિકારીની નોંધો", "Next steps": "આગળના પગલાં",
           "DRAFT": "મુસદ્દો", "Day": "દિવસ"},
    "pa": {"Draft Case Investigation Report": "ਖਰੜਾ ਕੇਸ ਜਾਂਚ ਰਿਪੋਰਟ", "Case Diary (Draft)": "ਕੇਸ ਡਾਇਰੀ (ਖਰੜਾ)",
           "Brief facts of the case": "ਕੇਸ ਦੇ ਸੰਖੇਪ ਤੱਥ", "Persons recorded": "ਦਰਜ ਵਿਅਕਤੀ", "Chronology": "ਘਟਨਾਕ੍ਰਮ",
           "Evidence collected": "ਇਕੱਠੇ ਕੀਤੇ ਸਬੂਤ", "Analytical findings": "ਵਿਸ਼ਲੇਸ਼ਣਾਤਮਕ ਨਤੀਜੇ",
           "Hypotheses tested": "ਪਰਖੀਆਂ ਗਈਆਂ ਧਾਰਨਾਵਾਂ", "Pending investigation": "ਬਾਕੀ ਜਾਂਚ",
           "Prior records (context only)": "ਪਿਛਲੇ ਰਿਕਾਰਡ (ਸਿਰਫ਼ ਸੰਦਰਭ)", "Uncertainties and limitations": "ਅਨਿਸ਼ਚਿਤਤਾਵਾਂ ਅਤੇ ਸੀਮਾਵਾਂ",
           "Evidence integrity": "ਸਬੂਤ ਦੀ ਅਖੰਡਤਾ", "Information received": "ਪ੍ਰਾਪਤ ਜਾਣਕਾਰੀ", "Statements recorded": "ਦਰਜ ਬਿਆਨ",
           "Steps taken / evidence collected": "ਚੁੱਕੇ ਕਦਮ / ਇਕੱਠੇ ਕੀਤੇ ਸਬੂਤ", "Circumstances ascertained": "ਪਤਾ ਲੱਗੇ ਹਾਲਾਤ",
           "Places visited": "ਦੌਰਾ ਕੀਤੇ ਸਥਾਨ", "Investigator entries": "ਜਾਂਚ ਅਧਿਕਾਰੀ ਦੀਆਂ ਐਂਟਰੀਆਂ", "Next steps": "ਅਗਲੇ ਕਦਮ",
           "DRAFT": "ਖਰੜਾ", "Day": "ਦਿਨ"},
}


def label(text: str, lang: str) -> str:
    return LABELS.get(lang, {}).get(text, text)
