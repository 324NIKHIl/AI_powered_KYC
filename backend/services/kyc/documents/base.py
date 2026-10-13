"""Shared context + preamble for every document verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from models.verification import AadhaarQrResult, DocumentType, ExtractedFields, FieldValidation
from services.kyc.config import tamper_suspicious_threshold
from services.kyc.quality import QualityReport
from services.kyc.result import CheckOutcome, DocumentVerification
from services.kyc.tampering import TamperReport

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


@dataclass
class DocContext:
    doc_type: DocumentType
    img: np.ndarray
    lines: list[str]
    full_text: str
    fields: ExtractedFields
    validation: FieldValidation
    quality: QualityReport
    tamper: TamperReport
    face_extracted: bool = False
    aadhaar_qr: Optional[AadhaarQrResult] = None
    text_upper: str = field(init=False)

    def __post_init__(self) -> None:
        self.text_upper = self.full_text.translate(DEVANAGARI_DIGITS).upper()


def start(ctx: DocContext, type_name: str, label: str) -> DocumentVerification:
    """Common layers 1-3: detection, OCR sanity, image quality, tamper heuristics."""
    v = DocumentVerification(document_type=type_name)
    v.document_detected = ctx.doc_type != DocumentType.UNKNOWN
    v.ocr_success = len(ctx.full_text.strip()) >= 15
    v.add("document_detected", f"{label} detected" if v.document_detected else "Document type not recognised",
          CheckOutcome.PASS if v.document_detected else CheckOutcome.WARN)
    v.add("ocr", "OCR completed" if v.ocr_success else "OCR could not read the document",
          CheckOutcome.PASS if v.ocr_success else CheckOutcome.WARN)
    if not v.ocr_success:
        v.unreadable = True

    q = ctx.quality
    if q.unusable:
        v.unreadable = True
        v.add("image_quality", "Image quality", CheckOutcome.WARN, "; ".join(q.issues).capitalize())
    elif q.issues:
        v.add("image_quality", "Image quality", CheckOutcome.WARN, "; ".join(q.issues).capitalize())
    else:
        v.add("image_quality", "Image quality acceptable", CheckOutcome.PASS)

    v.tampering_score = ctx.tamper.score
    v.tampering_detected = ctx.tamper.score >= tamper_suspicious_threshold()
    if v.tampering_detected:
        v.add("tampering", "Document analysis", CheckOutcome.FAIL,
              "Document manipulation indicators: " + "; ".join(ctx.tamper.indicators))
    elif ctx.tamper.score >= 0.35:
        v.add("tampering", "Document analysis", CheckOutcome.WARN,
              "Possible editing artefacts: " + "; ".join(ctx.tamper.indicators))
    else:
        v.add("tampering", "Document analysis found no manipulation indicators", CheckOutcome.PASS,
              "Heuristic analysis only — this does not prove the document is genuine")
    return v
