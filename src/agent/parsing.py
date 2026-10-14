"""Deterministic parsing for the agent (C1). No LLM, no network.

The LLM only points at WORDS in the user's message (it returns quotes). Everything numeric or calendar-like is read
here, with exact rules, so a language model can never invent or rescale a value, a date or a quantity.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal, InvalidOperation

# --------------------------------------------------------------------------- text
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_QUOTES = dict.fromkeys(map(ord, "‘’‚‛′"), "'")
_QUOTES.update(dict.fromkeys(map(ord, "“”„‟″"), '"'))


def norm_ws(s: str | None) -> str:
    """Lowercase, unify dashes and quotes, collapse whitespace. Used to compare a quote with the message."""
    s = unicodedata.normalize("NFKC", s or "").translate(_DASHES).translate(_QUOTES)
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in(quote: str | None, message: str | None) -> bool:
    """True when `quote` (a non-empty string) appears in `message` (whitespace and case insensitive)."""
    q = norm_ws(quote)
    return bool(q) and q in norm_ws(message)


# --------------------------------------------------------------------------- numbers and money
_MULT = {
    "k": Decimal(1_000), "thousand": Decimal(1_000),
    "lakh": Decimal(100_000), "lakhs": Decimal(100_000), "lac": Decimal(100_000), "lacs": Decimal(100_000),
    "million": Decimal(1_000_000), "mn": Decimal(1_000_000),
    "crore": Decimal(10_000_000), "crores": Decimal(10_000_000), "cr": Decimal(10_000_000),
    "billion": Decimal(1_000_000_000), "bn": Decimal(1_000_000_000),
}
_NUM = re.compile(
    r"(?<![\w.])(?P<n>\d[\d,]*(?:\.\d+)?|\.\d+)(?!\d)(?:\s*(?P<m>thousand|lakhs?|lacs?|million|mn|crores?|billion|bn|cr|k)(?![A-Za-z]))?",
    re.I)


def parse_number(text: str | None) -> Decimal | None:
    """First number in `text`. Handles 1,000,000 / 10,00,000 / 2.5 million / 10 lakh / 1.2 crore / 500k. None if there is none."""
    m = _NUM.search(text or "")
    if not m:
        return None
    raw = m.group("n").replace(",", "")
    try:
        d = Decimal(raw)
    except InvalidOperation:
        return None
    if m.group("m"):
        d *= _MULT[m.group("m").lower()]
    return d


_CUR = [
    ("USD", r"\$|\busd\b|\bus\s*dollars?\b|\bdollars?\b"),
    ("EUR", r"€|\beur\b|\beuros?\b"),
    ("GBP", r"£|\bgbp\b|\bpounds?\b"),
    ("CNY", r"\bcny\b|\brmb\b|\byuan\b"),
    ("AED", r"\baed\b|\bdirhams?\b"),
    ("JPY", r"\bjpy\b|\byen\b"),
    ("INR", r"\binr\b"),
    ("PKR", r"\bpkr\b|\brs\b\.?|\brupees?\b|₨"),
]


def detect_currency(text: str | None) -> str | None:
    t = text or ""
    for code, pat in _CUR:
        if re.search(pat, t, re.I):
            return code
    return None


def parse_amount(text: str | None) -> tuple[Decimal | None, str | None]:
    """(number, currency code or None) from phrases like 'Rs. 2.5 million', 'PKR 10 lakh', '$10,000'."""
    return parse_number(text), detect_currency(text)


def parse_quantity(text: str | None) -> tuple[Decimal | None, str | None]:
    """(number, unit word) from '5,000 kg', '10 sets', '2 MT'. The unit is the word right after the number (lowercased) or None."""
    m = _NUM.search(text or "")
    n = parse_number(text)
    if m is None or n is None:
        return None, None
    rest = (text or "")[m.end():]
    u = re.match(r"\s*([A-Za-z][A-Za-z.\-/]*)", rest)
    unit = u.group(1).lower().rstrip(".") if u else None
    return n, unit


def dec_str(d: Decimal) -> str:
    """Plain decimal string without exponent or trailing zeros ('1800', '2.5')."""
    s = format(d.normalize(), "f")
    return s


# --------------------------------------------------------------------------- yes / no / unknown / enums
_YES = {"yes", "y", "yeah", "yep", "yup", "true", "correct", "right", "sure", "affirmative", "haan", "han", "ji", "ha", "ok", "okay"}
_NO = {"no", "n", "nope", "nah", "false", "negative", "nahi", "nahin", "na", "not"}
_UNKNOWN = re.compile(r"^\s*(?:i\s+)?(?:do\s*n'?t|dont|do not)\s+know\b|^\s*(?:not sure|unsure|unknown|no idea|n/?a|skip|pass|idk|dunno)\b|\bno idea\b", re.I)


def is_unknown(text: str | None) -> bool:
    return bool(_UNKNOWN.search(norm_ws(text)))


_FILLER = {"it", "is", "isn't", "are", "aren't", "we", "i", "do", "don't", "does", "doesn't", "was", "were", "not", "no", "yes", "sure", "really", "that", "this", "so", "please"}


def is_bare_yes_no(text: str | None) -> bool:
    """True for answers that are only a yes or a no ('no', 'Yes, it is', 'not really'), which say nothing about the goods."""
    words = re.findall(r"[a-z']+", norm_ws(text))
    return bool(words) and all(w in _YES or w in _NO or w in _FILLER for w in words)


def parse_bool(text: str | None) -> bool | None:
    """yes/no (English and common Urdu transliterations). None when unclear or when both polarities appear."""
    t = norm_ws(text)
    if is_unknown(t):
        return None
    words = re.findall(r"[a-z']+", t)
    yes = any(w in _YES for w in words)
    no = any(w in _NO for w in words)
    if yes == no:
        return None
    return yes


def parse_enum(text: str | None, allowed: list) -> str | None:
    """The one allowed value mentioned in `text` (case insensitive, whole word). None if none or several."""
    t = norm_ws(text)
    hits = []
    for a in allowed:
        s = norm_ws(str(a))
        if s and re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", t):
            hits.append(a)
    return hits[0] if len(hits) == 1 else None


def parse_registration(text: str | None) -> str | None:
    """'registered' / 'unregistered' for the Sales Tax Act status. 'not registered', 'non-registered' count as unregistered."""
    t = norm_ws(text)
    if re.search(r"\bunregistered\b|\bnot\s+(?:sales\s*tax\s+)?registered\b|\bnon[\s-]*registered\b|\bnot\s+a\s+registered\b|\bnot\s+(?:yet\s+)?registered\b", t):
        return "unregistered"
    if re.search(r"(?<![a-z])registered\b", t):
        return "registered"
    return None


def parse_vehicle_form(text: str | None) -> str | None:
    t = norm_ws(text)
    ckd = bool(re.search(r"\bckd\b|completely knocked[\s-]*down", t))
    cbu = bool(re.search(r"\bcbu\b|completely built|built[\s-]*up unit", t))
    return "CKD" if ckd and not cbu else "CBU" if cbu and not ckd else None


# --------------------------------------------------------------------------- dates
_MON3 = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def _mk(y, m, d) -> dt.date | None:
    """Build a date from year, month (number or month name) and day. None if invalid."""
    try:
        month = _MON3[str(m).lower()[:3]] if not str(m).isdigit() else int(m)
        return dt.date(int(y), month, int(d))
    except (ValueError, KeyError):
        return None


def parse_date_text(text: str | None) -> dt.date | None:
    """A calendar date written in the text, day-first for numeric forms. None if there is none or it is ambiguous/invalid.

    Accepts 2026-07-15, 15/07/2026, 15-07-2026, 15.07.2026, 15 July 2026, 15th Jul 2026, July 15 2026, July 15, 2026."""
    t = norm_ws(text)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return _mk(m.group(1), m.group(2), m.group(3))
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", t)
    if m:
        return _mk(m.group(3), m.group(2), m.group(1))
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s,.-]*(?:of\s+)?{_MON}\b[\s,.-]*(\d{{4}})\b", t)
    if m:
        return _mk(m.group(3), m.group(2), m.group(1))
    m = re.search(rf"\b{_MON}\b[\s,.-]*(\d{{1,2}})(?:st|nd|rd|th)?[\s,.-]+(\d{{4}})\b", t)
    if m:
        return _mk(m.group(3), m.group(1), m.group(2))
    return None


_TODAY_WORDS = re.compile(r"\b(today|aaj|right now|as of now|current date)\b", re.I)


def says_today(text: str | None) -> bool:
    return bool(_TODAY_WORDS.search(text or ""))


# --------------------------------------------------------------------------- tariff codes and fiscal years
_C8_DOT = re.compile(r"(?<![\d.])(\d{4})\.(\d{4})(?![\d])")
_C8_RAW = re.compile(r"(?<![\d.,])(\d{8})(?![\d.,])")
_C6_DOT = re.compile(r"(?<![\d.])(\d{4})\.(\d{2})(?![\d.])")
_C4_WORD = re.compile(r"\b(?:heading|hs(?:\s*code)?|pct(?:\s*code)?|tariff\s*code|code)\s*[:#-]?\s*(\d{2}\.\d{2}|\d{4})(?!\d|\.\d)", re.I)


_CODE_WORD_BEFORE = re.compile(r"(?:heading|hs(?:\s*code)?|pct(?:\s*code)?|tariff\s*code|code)\s*[:#-]?\s*$", re.I)


def find_pct_codes(text: str | None) -> list[dict]:
    """PCT/HS codes written in the text: [{'code': digits (8, 6 or 4), 'trusted': bool}], in order, no duplicates.

    trusted=True : written like 6109.1000, or introduced by a word such as 'code', 'HS', 'PCT', 'heading'.
    trusted=False: looks like a code but could be an amount (61091000 with no dot, or 1234.56). The caller must check it
                   against the tariff and ignore it when it is not a tariff line / heading."""
    t = text or ""
    found: list[tuple[int, str, bool]] = []
    for m in _C8_DOT.finditer(t):
        found.append((m.start(), m.group(1) + m.group(2), True))
    for m in _C8_RAW.finditer(t):
        found.append((m.start(), m.group(1), bool(_CODE_WORD_BEFORE.search(t[:m.start()]))))
    for m in _C6_DOT.finditer(t):
        if not any(abs(m.start() - p) < 2 for p, _, _ in found):
            found.append((m.start(), m.group(1) + m.group(2), bool(_CODE_WORD_BEFORE.search(t[:m.start()]))))
    for m in _C4_WORD.finditer(t):
        found.append((m.start(), re.sub(r"\D", "", m.group(1)), True))
    out: list[dict] = []
    for _, c, trusted in sorted(found):
        for o in out:
            if o["code"] == c:
                o["trusted"] = o["trusted"] or trusted
                break
        else:
            out.append({"code": c, "trusted": trusted})
    return out


def display_code(code: str) -> str:
    """'61091000' -> '6109.1000'; 4 and 6 digit codes get a dot after the fourth digit when they have more."""
    c = re.sub(r"\D", "", code or "")
    return f"{c[:4]}.{c[4:]}" if len(c) > 4 else c


_FY = re.compile(r"(?:\b(?:fy|f\.y\.|fiscal\s*year|financial\s*year)\s*'?\s*(\d{2,4})\s*[-/]\s*(\d{2,4})\b|(?<![\d-])(20\d{2})\s*[-/]\s*(\d{2})(?![\d-]))", re.I)


def unsupported_fiscal_year(text: str | None, supported=((2025, 26), (2026, 27))) -> str | None:
    """A fiscal year written in the text (FY2024-25, financial year 2023/24, 2024-25) that is NOT supported, as 'YYYY-YY', else None.
    ISO dates such as 2026-07-15 are not fiscal years (the second number must be the next year)."""
    for m in _FY.finditer(text or ""):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        s = int(a) + 2000 if len(a) == 2 else int(a)
        e = int(b[-2:])
        if e != (s + 1) % 100:
            continue
        if (s, e) not in supported:
            return f"{s}-{e:02d}"
    return None
