"""
Document Service — orchestrates the full document verification pipeline:
upload → preprocess → OCR → field extraction → validation → face crop → scoring
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

from models.verification import (
    AadhaarQrResult,
    DocumentType,
    ExtractedFields,
    FieldValidation,
    DocumentUploadResponse,
)
from services.aadhaar_qr_service import process_aadhaar_qr
from services.kyc.document_verification import verify_document
from services.kyc.result import DocumentVerification
from services.ocr_service import (
    extract_text_full, extract_text_tiles, merge_lines, needs_tile_pass, parse_extracted_fields,
)
from utils.image_processing import (
    extract_face_mtcnn,
    save_image,
    save_upload_bytes,
)
from utils.validators import validate_name, validate_dob, validate_id_number

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")


async def process_document(
    file_bytes: bytes,
    original_filename: str,
    session_id: str,
) -> tuple[DocumentUploadResponse, DocumentVerification]:
    """
    Full document verification pipeline.
    Steps: save → preprocess → OCR → parse → validate → face extract → QR → evidence-based
    verification → score. Returns the API response and the full verification (incl. the
    server-side-only provider name, which is not part of the response).
    """
    # ── 1. Save upload ────────────────────────────────────────────────────────
    doc_dir  = os.path.join(UPLOAD_DIR, "documents")
    doc_path, raw_img = await save_upload_bytes(file_bytes, doc_dir, original_filename)
    logger.info("[%s] Document saved: %s shape=%s", session_id, doc_path, raw_img.shape)

    # ── 2. OCR ────────────────────────────────────────────────────────────────
    lines, full_text = extract_text_full(raw_img)
    logger.info("[%s] OCR extracted %d text lines", session_id, len(lines))

    # ── 3. Field parsing ──────────────────────────────────────────────────────
    doc_type, fields = parse_extracted_fields(lines, full_text)
    logger.info("[%s] Detected document type: %s", session_id, doc_type)

    # Quick pass came up short (phone photos, glare, mixed-script cards) → also read zoomed-in tiles
    if needs_tile_pass(fields):
        logger.info("[%s] Name/DOB/ID incomplete after the quick OCR pass — running zoomed tile pass", session_id)
        lines, full_text = merge_lines(lines, extract_text_tiles(raw_img))
        doc_type, fields = parse_extracted_fields(lines, full_text)
        logger.info("[%s] Re-parsed after tile pass: type=%s", session_id, doc_type)

    # ── 4. Field validation ───────────────────────────────────────────────────
    validation = FieldValidation(
        name=validate_name(fields.name),
        dob=validate_dob(fields.dob),
        id_number=validate_id_number(fields.id_number, doc_type),
    )
    # Field values are personal data — log only which fields validated, never their contents
    logger.info("[%s] OCR field validation=%s", session_id, validation.model_dump())

    # ── 5. Face extraction from document ─────────────────────────────────────
    face_img: Optional[np.ndarray] = extract_face_mtcnn(raw_img)
    face_path: Optional[str] = None
    if face_img is not None:
        face_dir  = os.path.join(UPLOAD_DIR, "faces")
        face_path = save_image(face_img, face_dir, prefix=f"doc_face_{session_id}")
        logger.info("[%s] Document face saved: %s shape=%s", session_id, face_path, face_img.shape)
    else:
        logger.warning("[%s] No face found in document", session_id)

    # ── 6. Aadhaar Secure QR (present on e-Aadhaar prints; PVC cards have it on the back) ──
    aadhaar_qr: Optional[AadhaarQrResult] = None
    if doc_type in (DocumentType.AADHAAR, DocumentType.UNKNOWN):
        aadhaar_qr = process_aadhaar_qr(raw_img, session_id, fields, validation)
        if not aadhaar_qr.found and doc_type == DocumentType.UNKNOWN:
            aadhaar_qr = None

    if aadhaar_qr and aadhaar_qr.found and doc_type == DocumentType.UNKNOWN:
        doc_type = DocumentType.AADHAAR   # a decoded Aadhaar QR identifies the document

    # ── 7. Evidence-based verification (format → crypto/QR/MRZ → external → fraud analysis) ──
    verification = await verify_document(
        doc_type=doc_type, img=raw_img, lines=lines, full_text=full_text, fields=fields,
        validation=validation, face_extracted=face_img is not None, aadhaar_qr=aadhaar_qr,
        raw_bytes=file_bytes,
    )

    # ── 8. Confidence score ───────────────────────────────────────────────────
    confidence = _compute_document_confidence(validation, face_img is not None, doc_type)
    logger.info(
        "[%s] Document confidence=%.4f threshold=%.4f",
        session_id,
        confidence,
        float(os.getenv("DOCUMENT_CONFIDENCE_THRESHOLD", "0.75")),
    )

    return DocumentUploadResponse(
        session_id=session_id,
        document_type=doc_type,
        extracted_fields=fields,
        field_validation=validation,
        document_confidence_score=round(confidence, 4),
        document_face_extracted=face_img is not None,
        document_face_path=face_path,
        aadhaar_qr=aadhaar_qr,
        ocr_text=full_text,
        verification=verification.model_dump(mode="json"),
        message=_build_message(confidence, validation, face_img is not None, verification),
    ), verification


async def process_aadhaar_qr_upload(
    file_bytes: bytes,
    original_filename: str,
    session_id: str,
    ocr_fields: ExtractedFields,
    validation: FieldValidation,
) -> AadhaarQrResult:
    """Second upload for cards whose QR is on the other side (e.g. PVC Aadhaar back)."""
    doc_dir = os.path.join(UPLOAD_DIR, "documents")
    qr_path, img = await save_upload_bytes(file_bytes, doc_dir, original_filename)
    logger.info("[%s] Aadhaar QR side saved: %s shape=%s", session_id, qr_path, img.shape)
    return process_aadhaar_qr(img, session_id, ocr_fields, validation)


# ── Confidence scoring ────────────────────────────────────────────────────────

def _compute_document_confidence(
    validation: FieldValidation,
    face_extracted: bool,
    doc_type: DocumentType,
) -> float:
    """
    Weighted confidence score based on:
    - valid name        → 0.25
    - valid dob         → 0.20
    - valid id_number   → 0.35  (most important — confirms the doc is real)
    - face extracted    → 0.20
    """
    score = 0.0
    if validation.name:
        score += 0.25
    if validation.dob:
        score += 0.20
    if validation.id_number:
        score += 0.35
    if face_extracted:
        score += 0.20

    # Slight penalty if document type is UNKNOWN
    if doc_type == DocumentType.UNKNOWN:
        score *= 0.80

    return round(min(score, 1.0), 4)


def _build_message(
    confidence: float,
    validation: FieldValidation,
    face_extracted: bool,
    verification: DocumentVerification,
) -> str:
    """
    A readable-document message — never "verified" unless the evidence engine says VALID.
    (OCR confidence only says how well we READ the document, not whether it is authentic.)
    """
    if verification.status.value == "VALID":
        return "Document authenticity confirmed"
    if verification.status.value in ("INVALID", "SUSPICIOUS"):
        return verification.summary
    if not validation.id_number:
        return "Document read, but its ID number could not be validated. " + verification.summary
    if not face_extracted:
        return "Document read, but no face was detected — face verification may fail. " + verification.summary
    return verification.summary or f"Document read with {confidence:.0%} confidence"
