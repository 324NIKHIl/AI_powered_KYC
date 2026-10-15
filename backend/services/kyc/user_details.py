"""
Compare the details the user typed in (name, date of birth, chosen document type)
with what OCR read from the uploaded document.

Each check is True (agrees), False (disagrees) or None (cannot be compared — nothing was entered,
or nothing could be read from the document). Only booleans are returned, never the values, so the
response does not echo the typed values back. The phone number is stored but never compared
(identity documents do not carry one).
"""

from __future__ import annotations

from typing import Any, Optional

from models.verification import DocumentType, ExtractedFields
from services.kyc.text_utils import dobs_match, names_match

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


def compare_declared_details(
    *,
    declared_type: DocumentType,
    detected_type: DocumentType,
    full_name: str,
    dob: str,
    extracted: ExtractedFields,
) -> dict[str, Any]:
    full_name, dob = full_name.strip(), dob.strip()

    def check(entered: str, read: Optional[str], same) -> Optional[bool]:
        if not entered or not read:
            return None
        return bool(same(entered, read))

    checks = {
        "document_type": (
            None if detected_type == DocumentType.UNKNOWN else declared_type == detected_type
        ),
        "name": check(full_name, extracted.name, names_match),
        "dob": check(dob, extracted.dob, dobs_match),
    }
    compared = [v for v in checks.values() if v is not None]
    return {
        **checks,
        "mismatches": [k for k, v in checks.items() if v is False],
        # True only when something was compared and nothing disagreed
        "all_match": bool(compared) and all(compared),
    }
