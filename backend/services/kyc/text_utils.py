"""Shared text/date/name helpers for the document verifiers."""

from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Optional

_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d %B %Y", "%d%b%Y", "%d-%b-%Y", "%d %b %y", "%b %d %Y", "%B %d, %Y",
)

_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
    r"|\d{1,2}[ \-][A-Za-z]{3,9}[ \-,]+\d{2,4})\b"
)


def parse_date(value: Optional[str], *, two_digit_pivot: Optional[int] = None) -> Optional[date]:
    """Parse a date in the formats seen on identity documents. None if unparseable."""
    if not value:
        return None
    value = re.sub(r"\s+", " ", value.strip().strip(".,"))
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        if "%y" in fmt:
            pivot = two_digit_pivot if two_digit_pivot is not None else date.today().year % 100
            century = 1900 if parsed.year % 100 > pivot else 2000
            parsed = parsed.replace(year=century + parsed.year % 100)
        return parsed
    return None


def find_dates(text: str) -> list[date]:
    """All dates in `text`, in order of appearance (duplicates removed)."""
    seen: list[date] = []
    for match in _DATE_RE.finditer(text):
        parsed = parse_date(match.group(1))
        if parsed and parsed not in seen:
            seen.append(parsed)
    return seen


def normalise_name(name: str) -> str:
    return re.sub(r"[^A-Z ]", "", re.sub(r"[.\-']", " ", name.upper())).strip()


def names_match(a: Optional[str], b: Optional[str], ratio: float = 0.80) -> bool:
    """Order-insensitive, typo-tolerant name comparison (OCR noise, initials, swapped order)."""
    if not a or not b:
        return False
    ta, tb = normalise_name(a).split(), normalise_name(b).split()
    if not ta or not tb:
        return False
    if sorted(ta) == sorted(tb):
        return True

    def tokens_covered(small: list[str], large: list[str]) -> bool:
        pool = list(large)
        for token in small:
            best = max(pool, key=lambda t: _token_score(token, t), default=None)
            if best is None or _token_score(token, best) < ratio:
                return False
            pool.remove(best)
        return True

    # Every token of the shorter name must be found in the longer one (middle names may be omitted)
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return tokens_covered(small, large)


def _token_score(a: str, b: str) -> float:
    if len(a) == 1 or len(b) == 1:                      # initial vs full name
        return 1.0 if a[0] == b[0] else 0.0
    return SequenceMatcher(None, a, b).ratio()


def dobs_match(a: Optional[str], b: Optional[str]) -> bool:
    da, db = parse_date(a), parse_date(b)
    return bool(da and db and da == db)


def clean_alnum(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def fuzzy_contains(haystack: str, needle: str, ratio: float = 0.85) -> bool:
    """True if `needle` (e.g. a surname) appears in `haystack`, tolerating OCR errors."""
    needle = clean_alnum(needle)
    haystack = clean_alnum(haystack)
    if len(needle) < 2:
        return False
    if needle in haystack:
        return True
    n = len(needle)
    for i in range(0, max(1, len(haystack) - n + 1)):
        if SequenceMatcher(None, haystack[i:i + n], needle).ratio() >= ratio:
            return True
    return False


def labelled_value(lines: list[str], labels: tuple[str, ...], value_pattern: str = r"[A-Za-z][A-Za-z .'\-]{2,60}") -> Optional[str]:
    """
    Value printed after a label — on the same line ("Name: Rahul Kumar") or on the next line.
    Works line by line so a value can never bleed into the next field (OCR joins lines poorly).
    """
    for i, line in enumerate(lines):
        for label in labels:
            m = re.search(label, line, re.IGNORECASE)
            if not m:
                continue
            for candidate in (line[m.end():], lines[i + 1] if i + 1 < len(lines) else ""):
                candidate = candidate.strip(" :.-\t")
                v = re.match(value_pattern, candidate)
                if v and v.group(0).strip():
                    return v.group(0).strip()
    return None
