"""
PAN verification, in layers:
  1. format  (structure + holder-type letter)       — necessary, NOT proof of authenticity
  2. OCR fields (number, name, DOB)
  3. consistency (independent PAN detection vs parsed number; 5th letter vs surname; card layout)
  4. external PAN provider (the only layer that can establish authenticity)
"""

from __future__ import annotations

import re
from typing import Optional

from services.kyc.documents.base import DocContext, start
from services.kyc.external import run_external_verification
from services.kyc.result import CheckOutcome, DocumentVerification, mask_identifier
from services.kyc.text_utils import clean_alnum

PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
# 4th character = holder category: P individual, C company, H HUF, F firm, A AOP, T trust,
# B BOI, L local authority, J artificial juridical person, G government
HOLDER_TYPES = {
    "P": "Individual", "C": "Company", "H": "Hindu Undivided Family", "F": "Firm", "A": "Association of Persons",
    "T": "Trust", "B": "Body of Individuals", "L": "Local Authority", "J": "Artificial Juridical Person",
    "G": "Government",
}
_TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
_TO_LETTER = {v: k for k, v in {"O": "0", "I": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}.items()}
LAYOUT_MARKERS = ("INCOME TAX", "PERMANENT ACCOUNT", "GOVT. OF INDIA", "GOVT OF INDIA", "GOVERNMENT OF INDIA")


def pan_format_valid(pan: Optional[str]) -> bool:
    return bool(pan and PAN_RE.fullmatch(pan.strip().upper()) and pan.strip().upper()[3] in HOLDER_TYPES)


def _repair(token: str, max_changes: int = 2) -> Optional[str]:
    """Fix OCR letter/digit confusions at the positions where PAN requires a specific class."""
    if len(token) != 10:
        return None
    out, changes = [], 0
    for i, ch in enumerate(token):
        want_digit = 5 <= i <= 8
        fixed = ch
        if want_digit and ch.isalpha():
            fixed = _TO_DIGIT.get(ch, ch)
        elif not want_digit and ch.isdigit():
            fixed = _TO_LETTER.get(ch, ch)
        changes += fixed != ch
        out.append(fixed)
    repaired = "".join(out)
    return repaired if changes <= max_changes and PAN_RE.fullmatch(repaired) else None


def detect_pan_candidates(text: str, *, strict: bool = False) -> list[str]:
    """
    Independent pass over the raw OCR text (distinct from the parsed id_number field).
    Strict matches are exact PAN-shaped strings. Unless `strict`, OCR-repaired matches are
    only offered when no exact match exists (so repairs can never invent a second PAN).
    """
    cleaned = clean_alnum(text)
    exact: list[str] = []
    for m in re.finditer(r"(?=([A-Z]{5}[0-9]{4}[A-Z]))", cleaned):
        if m.group(1) not in exact:
            exact.append(m.group(1))
    if exact or strict:
        return exact
    repaired: list[str] = []
    for m in re.finditer(r"(?=([A-Z0-9]{10}))", cleaned):
        pan = _repair(m.group(1))
        if pan and pan not in repaired:
            repaired.append(pan)
    return repaired


def verify_sync(ctx: DocContext) -> tuple[DocumentVerification, Optional[str]]:
    v = start(ctx, "PAN", "PAN card")
    parsed = (ctx.fields.id_number or "").strip().upper() or None
    candidates = detect_pan_candidates(ctx.full_text)
    exact_candidates = detect_pan_candidates(ctx.full_text, strict=True)
    pan = parsed if pan_format_valid(parsed) else None

    # Layer 1 — format
    if parsed is None and not candidates:
        v.format_valid = None
        v.add("pan_format", "PAN number", CheckOutcome.WARN, "No PAN number could be read from the document")
        return v, None
    if pan is None:
        repaired = next((c for c in candidates if pan_format_valid(c)), None)
        if repaired:
            pan = repaired
            v.add("pan_ocr_repair", "PAN corrected for OCR letter/digit confusion", CheckOutcome.INFO)
    if pan is None:
        v.format_valid = False
        v.add("pan_format", "PAN format", CheckOutcome.FAIL,
              "Value does not follow the PAN structure (5 letters, 4 digits, 1 letter with a valid holder-type letter)")
        return v, None
    v.format_valid = True
    v.add("pan_format", "PAN format valid", CheckOutcome.PASS,
          f"Holder type: {HOLDER_TYPES[pan[3]]}. Structure only — a well-formed PAN is not proof that it was issued")

    # Layer 3 — consistency
    others = [c for c in exact_candidates if c != pan and pan_format_valid(c)]
    if others:
        v.identity_consistent = False
        v.add("pan_consistent", "PAN number consistent across the document", CheckOutcome.FAIL,
              "More than one different PAN-like number is present on the document")
    else:
        v.add("pan_consistent", "PAN number consistent across the document", CheckOutcome.PASS)

    if pan[3] == "P" and ctx.fields.name:
        surname = ctx.fields.name.strip().split()[-1].upper()
        if pan[4] != surname[0]:
            v.add("pan_surname", "5th PAN letter matches the surname initial", CheckOutcome.WARN,
                  "For individuals the 5th letter is the surname's first letter — it does not match the name read")
        else:
            v.add("pan_surname", "5th PAN letter matches the surname initial", CheckOutcome.PASS)

    markers = sum(1 for m in LAYOUT_MARKERS if m in ctx.text_upper)
    if markers >= 2:
        v.add("pan_layout", "Document layout consistent with a PAN card", CheckOutcome.PASS)
    elif markers == 1:
        v.add("pan_layout", "Document layout consistent with a PAN card", CheckOutcome.WARN,
              "Only some expected PAN card text was found")
    else:
        v.add("pan_layout", "Document layout consistent with a PAN card", CheckOutcome.WARN,
              "Expected PAN card headings were not found")
    if not ctx.face_extracted:
        v.add("pan_photo", "Photo present on card", CheckOutcome.WARN, "No face found on the document")

    v.extracted = {"name": ctx.fields.name, "dob": ctx.fields.dob, "pan": mask_identifier(pan),
                   "holder_type": HOLDER_TYPES[pan[3]]}
    return v, pan


async def verify(ctx: DocContext) -> DocumentVerification:
    v, pan = verify_sync(ctx)
    if pan and not v.failed():
        await run_external_verification(
            v, "PAN", {"document_number": pan, "name": ctx.fields.name, "dob": ctx.fields.dob},
            label="PAN verified with external provider",
            expected_name=ctx.fields.name, expected_dob=ctx.fields.dob, document_text=ctx.full_text,
        )
    return v
