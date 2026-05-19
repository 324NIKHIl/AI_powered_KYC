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
    DocumentType,
    ExtractedFields,
    FieldValidation,
    DocumentUploadResponse,
)
from services.ocr_service import extract_text_full, parse_extracted_fields
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
) -> DocumentUploadResponse:
    """
    Full document verification pipeline.
    Steps: save → preprocess → OCR → parse → validate → face extract → score
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

    # ── 4. Field validation ───────────────────────────────────────────────────
    validation = FieldValidation(
        name=validate_name(fields.name),
        dob=validate_dob(fields.dob),
        id_number=validate_id_number(fields.id_number, doc_type),
    )
    logger.info(
        "[%s] OCR fields=%s validation=%s",
        session_id,
        fields.model_dump(),
        validation.model_dump(),
    )

    # ── 5. Face extraction from document ─────────────────────────────────────
    face_img: Optional[np.ndarray] = extract_face_mtcnn(raw_img)
    face_path: Optional[str] = None
    if face_img is not None:
        face_dir  = os.path.join(UPLOAD_DIR, "faces")
        face_path = save_image(face_img, face_dir, prefix=f"doc_face_{session_id}")
        logger.info("[%s] Document face saved: %s shape=%s", session_id, face_path, face_img.shape)
    else:
        logger.warning("[%s] No face found in document", session_id)

    # ── 6. Confidence score ───────────────────────────────────────────────────
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
        message=_build_message(confidence, validation, face_img is not None),
    )


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


def _build_message(confidence: float, validation: FieldValidation, face_extracted: bool) -> str:
    threshold = float(os.getenv("DOCUMENT_CONFIDENCE_THRESHOLD", "0.75"))
    if confidence >= threshold:
        return "Document verified successfully"
    if not validation.id_number:
        return "ID number could not be validated"
    if not face_extracted:
        return "Document processed but no face detected — face verification may fail"
    return f"Document verified with low confidence ({confidence:.0%})"
