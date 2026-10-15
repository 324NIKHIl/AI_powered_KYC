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
_AADHAAR_GROUPED_RE = re.compile(r"\b[2-9]\d{3}[\s\.,-]*\d{4}[\s\.,-]*\d{4}\b")
_PAN_RE      = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")
_PASSPORT_RE = re.compile(r"\b[A-Z]{1}[0-9]{7}\b")
_MRZ_LINE_RE = re.compile(r"P[<A-Z][A-Z<]{3}[A-Z<]{20,}")
_DL_RE = re.compile(r"\b[A-Z]{2}[\s\-]?\d{2}[\s\-]?(?:19|20)\d{2}[\s\-]?\d{7}\b")


# ── Name ─────────────────────────────────────────────────────────────────────

def validate_name(name: Optional[str]) -> bool:
    if not name or len(name.strip()) < 3:
        return False
    return bool(re.match(r"^[A-Za-z\s\.\-']{3,60}$", name.strip()))


# ── Date of Birth ─────────────────────────────────────────────────────────────

def validate_dob(dob: Optional[str]) -> bool:
    """Accept common formats: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD (or the year alone, as on some Aadhaar cards)."""
    if not dob:
        return False
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%Y"]   # "%Y": Aadhaar may print only the birth year
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
    """
    Format-level check of the primary identifier. NOTE: this is a *format* check only —
    it says nothing about authenticity (see services/kyc for the evidence-based verification).
    """
    if doc_type == DocumentType.AADHAAR:
        return validate_aadhaar(id_number)
    if doc_type == DocumentType.PAN:
        return validate_pan(id_number)
    if doc_type == DocumentType.PASSPORT:
        return validate_passport(id_number)
    # Other documents: the dedicated verifier validates its own number; keep a sanity bound here
    return bool(id_number and 4 <= len(id_number.strip()) <= 20)


# ── Document type detection from raw OCR text ─────────────────────────────────

def detect_document_type(text: str) -> DocumentType:
    upper = text.upper()
    squashed = re.sub(r"[^A-Z0-9<]", "", upper.replace(" ", ""))

    # Strong Aadhaar signals
    if any(kw in upper for kw in ["AADHAAR", "AADHAR", "UNIQUE IDENTIFICATION", "UIDAI", "ENROLMENT NO"]):
        return DocumentType.AADHAAR

    # Passport: a Machine Readable Zone, or the word itself
    if _MRZ_LINE_RE.search(squashed) and "<<" in squashed:
        return DocumentType.PASSPORT
    if re.search(r"\bPASSPORT\b", upper) and "PASSPORT SIZE" not in upper:
        return DocumentType.PASSPORT

    # Specific headings of the other supported documents
    if any(kw in upper for kw in ["INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER"]):
        return DocumentType.PAN
    if any(kw in upper for kw in ["DRIVING LICEN", "LICENCE TO DRIVE", "FORM OF LICENCE", "DRIVING PERMIT"]):
        return DocumentType.DRIVING_LICENCE
    if "CITIZENSHIP" in upper or "नागरिकता" in text:
        return DocumentType.CITIZENSHIP
    if any(kw in upper for kw in [
        "MARKSHEET", "MARK SHEET", "STATEMENT OF MARKS", "GRADE SHEET", "GRADE CARD", "SECONDARY SCHOOL CERTIFICATE",
        "SENIOR SCHOOL CERTIFICATE", "SECONDARY EDUCATION EXAMINATION", "SCHOOL LEVEL CERTIFICATE",
        "HIGHER SECONDARY", "BOARD OF SECONDARY EDUCATION", "RESULT OF", "PASS CERTIFICATE",
    ]):
        return DocumentType.EDUCATION

    # 12-digit number printed in groups of four ("4017 1397 4861"). Searched with
    # whitespace intact — stripping it first glues the number to neighbouring
    # words ("Male401713974861") so the word boundaries never match.
    if _AADHAAR_GROUPED_RE.search(text):
        return DocumentType.AADHAAR

    # Weaker PAN / licence / passport signals
    if re.search(r"\bPAN\b", upper) or _PAN_RE.search(upper):
        return DocumentType.PAN
    if _DL_RE.search(upper):
        return DocumentType.DRIVING_LICENCE
    if any(kw in upper for kw in ["REPUBLIC OF INDIA", "NATIONALITY"]) or _PASSPORT_RE.search(upper):
        return DocumentType.PASSPORT

    # College ID
    if any(kw in upper for kw in ["COLLEGE", "UNIVERSITY", "INSTITUTE", "STUDENT", "ENROLLMENT", "ROLL NO"]):
        return DocumentType.COLLEGE_ID

    return DocumentType.UNKNOWN
