"""
Field validators for KYC document data.
Each validator returns True/False and optionally a normalised value.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from models.verification import DocumentType


# ── ID-number patterns ────────────────────────────────────────────────────────
_AADHAAR_RE  = re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")
_PAN_RE      = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")
_PASSPORT_RE = re.compile(r"\b[A-Z]{1}[0-9]{7}\b")


# ── Name ─────────────────────────────────────────────────────────────────────

def validate_name(name: Optional[str]) -> bool:
    if not name or len(name.strip()) < 3:
        return False
    return bool(re.match(r"^[A-Za-z\s\.\-']{3,60}$", name.strip()))


# ── Date of Birth ─────────────────────────────────────────────────────────────

def validate_dob(dob: Optional[str]) -> bool:
    """Accept common formats: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD."""
    if not dob:
        return False
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(dob.strip(), fmt)
            # Basic sanity: age between 1 and 120
            age = (datetime.now() - parsed).days / 365
            return 1 <= age <= 120
        except ValueError:
            continue
    return False


# ── ID number ────────────────────────────────────────────────────────────────

def validate_aadhaar(id_number: Optional[str]) -> bool:
    if not id_number:
        return False
    clean = re.sub(r"\s", "", id_number)
    return bool(_AADHAAR_RE.match(clean)) and len(clean) == 12


def validate_pan(id_number: Optional[str]) -> bool:
    if not id_number:
        return False
    return bool(_PAN_RE.fullmatch(id_number.strip().upper()))


def validate_passport(id_number: Optional[str]) -> bool:
    if not id_number:
        return False
    return bool(_PASSPORT_RE.fullmatch(id_number.strip().upper()))


def validate_id_number(id_number: Optional[str], doc_type: DocumentType) -> bool:
    if doc_type == DocumentType.AADHAAR:
        return validate_aadhaar(id_number)
    if doc_type == DocumentType.PAN:
        return validate_pan(id_number)
    if doc_type == DocumentType.PASSPORT:
        return validate_passport(id_number)
    # College ID — just check it's non-empty and reasonable
    return bool(id_number and 4 <= len(id_number.strip()) <= 20)


# ── Document type detection from raw OCR text ─────────────────────────────────

def detect_document_type(text: str) -> DocumentType:
    upper = text.upper()

    # Strong Aadhaar signals
    if any(kw in upper for kw in ["AADHAAR", "AADHAR", "UNIQUE IDENTIFICATION"]):
        return DocumentType.AADHAAR
    if _AADHAAR_RE.search(re.sub(r"\s", "", text)):
        return DocumentType.AADHAAR

    # PAN signals
    if any(kw in upper for kw in ["INCOME TAX", "PERMANENT ACCOUNT", "PAN"]):
        return DocumentType.PAN
    if _PAN_RE.search(text.upper()):
        return DocumentType.PAN

    # Passport signals
    if any(kw in upper for kw in ["PASSPORT", "REPUBLIC OF INDIA", "NATIONALITY"]):
        return DocumentType.PASSPORT
    if _PASSPORT_RE.search(text.upper()):
        return DocumentType.PASSPORT

    # College ID
    if any(kw in upper for kw in ["COLLEGE", "UNIVERSITY", "INSTITUTE", "STUDENT", "ENROLLMENT", "ROLL NO"]):
        return DocumentType.COLLEGE_ID

    return DocumentType.UNKNOWN
