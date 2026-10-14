"""
DocumentVerificationService — the single entry point for document verification.

    detect type → image quality → OCR fields → document-specific validation
    → cryptographic / QR / MRZ → external provider → tamper analysis → decision engine

The OCR/type-detection steps already exist in services/ocr_service.py and are reused as-is;
this module takes their output and produces the unified DocumentVerification.
"""

from __future__ import annotations

import io
import logging
import time
from typing import Optional

import numpy as np
from PIL import Image

from models.verification import AadhaarQrResult, DocumentType, ExtractedFields, FieldValidation
from services.kyc import engine
from services.kyc.documents import aadhaar, citizenship, driving_licence, education, pan, passport
from services.kyc.documents.base import DocContext, start
from services.kyc.quality import assess_quality
from services.kyc.result import CheckOutcome, DocumentVerification
from services.kyc.tampering import analyse_tampering

logger = logging.getLogger(__name__)

TYPE_NAMES = {
    DocumentType.AADHAAR: "AADHAAR", DocumentType.PAN: "PAN", DocumentType.PASSPORT: "PASSPORT",
    DocumentType.DRIVING_LICENCE: "DRIVING_LICENCE", DocumentType.CITIZENSHIP: "CITIZENSHIP",
    DocumentType.EDUCATION: "EDUCATION", DocumentType.COLLEGE_ID: "COLLEGE_ID", DocumentType.UNKNOWN: "UNKNOWN",
}


def _is_jpeg(raw: Optional[bytes]) -> bool:
    if not raw:
        return True
    try:
        with Image.open(io.BytesIO(raw)) as im:
            return (im.format or "").upper() in ("JPEG", "MPO")
    except Exception:
        return False


def _unsupported(ctx: DocContext, type_name: str, label: str) -> DocumentVerification:
    """College ID / unknown documents: no authoritative verification mechanism exists."""
    v = start(ctx, type_name, label)
    v.add("doc_supported", "Authoritative verification available for this document type", CheckOutcome.WARN,
          "No verification mechanism exists for this document — manual review required")
    return v


async def verify_document(
    *,
    doc_type: DocumentType,
    img: np.ndarray,
    lines: list[str],
    full_text: str,
    fields: ExtractedFields,
    validation: FieldValidation,
    face_extracted: bool,
    aadhaar_qr: Optional[AadhaarQrResult] = None,
    raw_bytes: Optional[bytes] = None,
) -> DocumentVerification:
    started = time.perf_counter()
    type_name = TYPE_NAMES[doc_type]
    logger.info("document verification started type=%s", type_name)

    ctx = DocContext(
        doc_type=doc_type, img=img, lines=lines, full_text=full_text, fields=fields, validation=validation,
        quality=assess_quality(img),
        tamper=analyse_tampering(img, raw_bytes, source_is_jpeg=_is_jpeg(raw_bytes)),
        face_extracted=face_extracted, aadhaar_qr=aadhaar_qr,
    )

    try:
        if doc_type == DocumentType.AADHAAR:
            v = aadhaar.verify(ctx)
        elif doc_type == DocumentType.PAN:
            v = await pan.verify(ctx)
        elif doc_type == DocumentType.PASSPORT:
            v = await passport.verify(ctx)
        elif doc_type == DocumentType.DRIVING_LICENCE:
            v = await driving_licence.verify(ctx)
        elif doc_type == DocumentType.CITIZENSHIP:
            v = await citizenship.verify(ctx)
        elif doc_type == DocumentType.EDUCATION:
            v = await education.verify(ctx)
        elif doc_type == DocumentType.COLLEGE_ID:
            v = _unsupported(ctx, type_name, "College ID")
        else:
            v = _unsupported(ctx, type_name, "Document")
    except Exception:
        # A verifier bug must never crash the KYC workflow — and must never read as "verified"
        logger.exception("document verifier crashed type=%s", type_name)
        v = DocumentVerification(document_type=type_name)
        v.add("verifier_error", "Automated verification", CheckOutcome.WARN,
              "Automated verification failed unexpectedly — manual review required")
        v.unreadable = True

    engine.decide(v)
    v.processing_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "document verification finished type=%s status=%s evidence=%s provider=%s ms=%d",
        type_name, v.status.value, v.evidence_level.value, v.provider or "-", v.processing_ms,
    )
    return v
