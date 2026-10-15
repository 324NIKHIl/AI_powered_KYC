"""
Compare the details the user typed in (name, date of birth, chosen document type)
with what OCR read from the uploaded document.

Each check is True (agrees), False (disagrees) or None (cannot be compared — nothing was entered,
or nothing could be read from the document). Only booleans are returned, never the values, so the
response does not echo the typed values back. The phone number is stored but never compared
(identity documents do not carry one).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Optional

from models.verification import DocumentType, ExtractedFields
from services.kyc.text_utils import dobs_match, names_match, normalise_name, parse_date

# Document types a user may choose in the UI (the dropdown on step 2). Selecting one is mandatory.
SELECTABLE_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.AADHAAR,
    DocumentType.PASSPORT,
    DocumentType.CITIZENSHIP,
    DocumentType.PAN,
    DocumentType.DRIVING_LICENCE,
)


def parse_declared_type(value: Optional[str]) -> Optional[DocumentType]:
    """The chosen document type, or None when it is missing / not one of the selectable types."""
    try:
        doc_type = DocumentType((value or "").strip().lower())
    except ValueError:
        return None
    return doc_type if doc_type in SELECTABLE_DOCUMENT_TYPES else None


def name_in_text(full_name: str, text: str, ratio: float = 0.8) -> bool:
    """
    True when every word of the typed name appears (typo-tolerantly) somewhere in the raw OCR text.
    More robust than comparing against one parsed "name" line, which noisy OCR often gets wrong.
    """
    tokens = [t for t in normalise_name(full_name).split() if len(t) >= 2]
    words = re.findall(r"[A-Z]{2,}", (text or "").upper())
    if not tokens or not words:
        return False
    return all(
        any(w == t or (len(t) >= 4 and SequenceMatcher(None, t, w).ratio() >= ratio) for w in words)
        for t in tokens
    )


def _dobs_agree(entered: str, read: str) -> bool:
    """Full dates must match; a year-only DOB (printed that way on some Aadhaar cards) matches on the year."""
    if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", read):
        typed = parse_date(entered)
        return bool(typed and typed.year == int(read))
    return dobs_match(entered, read)


def compare_declared_details(
    *,
    declared_type: DocumentType,
    detected_type: DocumentType,
    full_name: str,
    dob: str,
    extracted: ExtractedFields,
    ocr_text: str = "",
) -> dict[str, Any]:
    full_name, dob = full_name.strip(), dob.strip()

    def check(entered: str, read: Optional[str], same) -> Optional[bool]:
        if not entered or not read:
            return None
        return bool(same(entered, read))

    # Name: agrees with the parsed name, or all its words are found in the raw OCR text.
    if not full_name:
        name_check: Optional[bool] = None
    elif extracted.name and names_match(full_name, extracted.name):
        name_check = True
    elif name_in_text(full_name, ocr_text):
        name_check = True
    else:
        name_check = False if extracted.name else None

    checks = {
        "document_type": (
            None if detected_type == DocumentType.UNKNOWN else declared_type == detected_type
        ),
        "name": name_check,
        "dob": check(dob, extracted.dob, _dobs_agree),
    }
    compared = [v for v in checks.values() if v is not None]
    return {
        **checks,
        "mismatches": [k for k, v in checks.items() if v is False],
        # True only when something was compared and nothing disagreed
        "all_match": bool(compared) and all(compared),
    }
