"""
OCR Service — text extraction and structured field parsing using EasyOCR.
Reader is initialised once (lazy singleton) to avoid per-request model loading.
"""

from __future__ import annotations

import re
import logging
from difflib import SequenceMatcher
from typing import Optional

import numpy as np

from models.verification import DocumentType, ExtractedFields
from utils.validators import detect_document_type
from utils.image_processing import enhance_contrast, deskew, preprocess_for_ocr

logger = logging.getLogger(__name__)

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        logger.info("Initialising EasyOCR reader (first-time model load)…")
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logger.info("EasyOCR ready")
    return _reader


# ── Main extraction function ──────────────────────────────────────────────────

def _normalise_for_dedupe(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def _looks_like_duplicate(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.88


def _sort_ocr_results(results: list[tuple]) -> list[tuple[str, float]]:
    def top_left(result: tuple) -> tuple[float, float]:
        box = result[0]
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        return min(ys), min(xs)

    sorted_results = sorted(results, key=top_left)
    return [(str(text).strip(), float(conf)) for _, text, conf in sorted_results if str(text).strip()]


def extract_text(img: np.ndarray) -> list[str]:
    """Run EasyOCR and return list of detected text strings."""
    reader = _get_reader()
    results = reader.readtext(
        img,
        detail=1,
        paragraph=False,
        width_ths=0.7,
        text_threshold=0.4,
        low_text=0.25,
        link_threshold=0.4,
    )
    lines = [text for text, _ in _sort_ocr_results(results)]
    logger.debug("OCR raw output: %s", lines)
    return lines


def extract_text_full(img: np.ndarray) -> tuple[list[str], str]:
    """
    Return both list and concatenated string.

    EasyOCR often performs better on the original image for printed IDs, while
    thresholding helps low-contrast scans. Run a small set of variants and keep
    the highest-confidence version of near-duplicate text.
    """
    reader = _get_reader()
    variants = [
        img,
        enhance_contrast(img),
        preprocess_for_ocr(deskew(enhance_contrast(img))),
    ]

    selected: list[tuple[str, float]] = []
    for variant in variants:
        results = reader.readtext(
            variant,
            detail=1,
            paragraph=False,
            width_ths=0.7,
            text_threshold=0.4,
            low_text=0.25,
            link_threshold=0.4,
        )
        for text, confidence in _sort_ocr_results(results):
            key = _normalise_for_dedupe(text)
            if len(key) < 2:
                continue
            duplicate_index = next(
                (
                    i
                    for i, (existing, _) in enumerate(selected)
                    if _looks_like_duplicate(key, _normalise_for_dedupe(existing))
                ),
                None,
            )
            if duplicate_index is None:
                selected.append((text, confidence))
            elif confidence > selected[duplicate_index][1]:
                selected[duplicate_index] = (text, confidence)

    lines = [text for text, _ in selected]
    logger.debug("OCR merged output: %s", lines)
    return lines, " ".join(lines)


# ── Field parsers ─────────────────────────────────────────────────────────────

def _parse_name(lines: list[str], doc_type: DocumentType) -> Optional[str]:
    """
    Name extraction heuristics per document type.
    Falls back to finding the longest capitalised line that looks like a name.
    """
    def is_name_candidate(value: str) -> bool:
        upper = value.upper()
        blocked = [
            "GOVERNMENT", "INCOME", "TAX", "DEPARTMENT", "AADHAAR", "VID",
            "SIGNATURE", "VERIFIED", "ACCOUNT", "NUMBER", "DOB", "DATE",
            "BIRTH", "ADDRESS", "MALE", "FEMALE", "INDIA",
        ]
        if any(word in upper for word in blocked):
            return False
        if re.search(r"\d", value):
            return False
        return bool(re.match(r"^[A-Za-z][A-Za-z\s\.\-']{2,59}$", value.strip()))

    def best_name_candidate(candidates: list[str]) -> Optional[str]:
        valid = [candidate.strip() for candidate in candidates if is_name_candidate(candidate)]
        if not valid:
            return None

        def score(candidate: str) -> tuple[int, int]:
            words = candidate.split()
            value = 0
            if len(words) == 2:
                value += 5
            elif len(words) == 3:
                value += 3
            if all(word[:1].isupper() and word[1:].islower() for word in words if word):
                value += 2
            if len(candidate) > 30:
                value -= 3
            return value, len(candidate)

        return max(valid, key=score)

    if doc_type in (DocumentType.AADHAAR, DocumentType.PAN):
        # Name usually appears after "Name:" or on its own line with title case
        for i, line in enumerate(lines):
            if re.search(r"\bNAME\b", line.upper()):
                # Try next line
                if i + 1 < len(lines):
                    candidate = lines[i + 1]
                    if is_name_candidate(candidate):
                        return candidate.strip().title()
                # Or same line after colon
                parts = re.split(r"[:|\-]", line, maxsplit=1)
                if len(parts) > 1 and is_name_candidate(parts[1]):
                    return parts[1].strip().title()

    if doc_type == DocumentType.AADHAAR:
        for i, line in enumerate(lines):
            if re.search(r"\b(C[/\\]?I?O|C1O|S[/\\]?O|D[/\\]?O|W[/\\]?O|CARE OF)\b", line.upper()):
                candidate = best_name_candidate(lines[max(0, i - 5):i])
                if candidate and len(candidate.split()) >= 2:
                    return candidate.title()

        for i, line in enumerate(lines):
            if line.strip().upper() == "TO":
                candidate = best_name_candidate(lines[i + 1:i + 12])
                if candidate and len(candidate.split()) >= 2:
                    return candidate.title()

    if doc_type == DocumentType.PASSPORT:
        # Passport MRZ line 2 or explicit surname/given name fields
        for i, line in enumerate(lines):
            if "SURNAME" in line.upper() or "GIVEN" in line.upper():
                parts = re.split(r"[:|\-]", line, maxsplit=1)
                if len(parts) > 1 and re.match(r"^[A-Za-z\s]{3,50}$", parts[1]):
                    return parts[1].strip().title()

    # Generic: find longest all-alpha title-case string
    candidates = [l for l in lines if is_name_candidate(l) and re.match(r"^[A-Z][a-z]+(\s+[A-Z][a-z]+){0,4}$", l)]
    if candidates:
        return max(candidates, key=len)

    return None


def _parse_dob(lines: list[str]) -> Optional[str]:
    """Find any date pattern in the text lines."""
    date_patterns = [
        r"\b(\d{2}/\d{2}/\d{4})\b",
        r"\b(\d{2}-\d{2}-\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{2}\s+[A-Za-z]{3}\s+\d{4})\b",
        r"\b(\d{2}\s+[A-Za-z]+\s+\d{4})\b",
    ]
    full_text = " ".join(lines)
    for pattern in date_patterns:
        match = re.search(pattern, full_text)
        if match:
            return match.group(1)
    return None


def _parse_gender(lines: list[str]) -> Optional[str]:
    full_text = " ".join(lines).upper()
    if re.search(r"\bMALE\b", full_text):
        if re.search(r"\bFEMALE\b", full_text):
            # Context — which comes first in the doc?
            fi = full_text.find("FEMALE")
            mi = full_text.find("MALE")
            return "Female" if fi < mi else "Male"
        return "Male"
    if re.search(r"\bFEMALE\b", full_text):
        return "Female"
    if re.search(r"\bM\b", full_text):
        return "Male"
    if re.search(r"\bF\b", full_text):
        return "Female"
    return None


def _parse_id_number(lines: list[str], doc_type: DocumentType) -> Optional[str]:
    full_text = " ".join(lines)

    if doc_type == DocumentType.AADHAAR:
        aadhaar_markers = ["YOUR AADHAAR NO", "AADHAAR NO", "AADHAAR NUMBER"]
        upper = full_text.upper()
        for marker in aadhaar_markers:
            marker_index = upper.find(marker)
            if marker_index == -1:
                continue
            window = full_text[marker_index:marker_index + 160]
            match = re.search(r"\b([2-9]\d{3})[\s\.,-]+(\d{4})[\s\.,-]+(\d{4})\b", window)
            if match:
                return "".join(match.groups())

        candidates = []
        for match in re.finditer(r"\b([2-9]\d{3})[\s\.,-]+(\d{4})[\s\.,-]+(\d{4})\b", full_text):
            context = full_text[max(0, match.start() - 25):match.start()].upper()
            if "VID" in context:
                continue
            candidates.append("".join(match.groups()))
        return candidates[-1] if candidates else None

    if doc_type == DocumentType.PAN:
        clean = re.sub(r"[^A-Z0-9]", "", full_text.upper())
        match = re.search(r"([A-Z]{5}[0-9]{4}[A-Z])", clean)
        return match.group(1) if match else None

    if doc_type == DocumentType.PASSPORT:
        match = re.search(r"\b([A-Z][0-9]{7})\b", full_text.upper())
        return match.group(1) if match else None

    # College ID — look for numeric roll numbers
    match = re.search(r"\b([A-Z0-9]{4,12})\b", full_text.upper())
    return match.group(1) if match else None


def _parse_address(lines: list[str]) -> Optional[str]:
    full_text = " ".join(lines)
    match = re.search(r"(?:Address|Addr)[:\-]?\s*(.+?)(?:\n|$)", full_text, re.IGNORECASE)
    return match.group(1).strip() if match else None


# ── Public API ────────────────────────────────────────────────────────────────

def parse_extracted_fields(lines: list[str], full_text: str) -> tuple[DocumentType, ExtractedFields]:
    """
    Detect document type and extract structured fields from OCR output.
    Returns (document_type, extracted_fields).
    """
    doc_type = detect_document_type(full_text)

    fields = ExtractedFields(
        name=_parse_name(lines, doc_type),
        dob=_parse_dob(lines),
        gender=_parse_gender(lines),
        id_number=_parse_id_number(lines, doc_type),
        address=_parse_address(lines),
    )
    return doc_type, fields
