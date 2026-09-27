"""
Document verification API routes.
POST /api/upload-document  — upload, OCR, extract fields, extract face
GET  /api/document/{session_id} — fetch session result
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from models.verification import AadhaarQrResult, DocumentUploadResponse, ExtractedFields, FieldValidation
from services.document_service import process_aadhaar_qr_upload, process_document
from services.verification_service import (
    create_session,
    generate_session_id,
    update_session,
    upsert_document_record,
    upsert_verification_fields,
)

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "application/pdf"}
MAX_BYTES     = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload-document",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload identity document for OCR and face extraction",
)
async def upload_document(
    file: UploadFile = File(..., description="JPG / PNG / PDF of identity document"),
    session_id: str  = Form(default=""),
):
    logger.info(
        "Document upload request filename=%s content_type=%s supplied_session=%s",
        file.filename,
        file.content_type,
        bool(session_id.strip()),
    )
    # ── Validate MIME type ────────────────────────────────────────────────────
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Allowed: JPG, PNG, PDF",
        )

    # ── Read bytes ────────────────────────────────────────────────────────────
    data = await file.read()
    logger.info("Document upload bytes=%d", len(data))
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 10 MB limit",
        )

    # ── Session ───────────────────────────────────────────────────────────────
    sid = session_id.strip() or generate_session_id()
    logger.info("[%s] Document upload session initialized", sid)

    # ── Process document pipeline ─────────────────────────────────────────────
    try:
        result = await process_document(data, file.filename or "document", sid)
    except Exception as exc:
        logger.exception("[%s] Document processing failed", sid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(exc)}",
        ) from exc

    # ── Persist session + verification record ─────────────────────────────────
    aadhaar_qr = result.aadhaar_qr.model_dump(mode="json") if result.aadhaar_qr else None
    session_data = {
        "document_face_path":        result.document_face_path,
        "document_confidence_score": result.document_confidence_score,
        "document_type":             result.document_type,
        "aadhaar_qr":                aadhaar_qr,
    }
    await create_session(sid, session_data)
    await upsert_document_record(sid, {
        "document_type":             result.document_type,
        "extracted_fields":          result.extracted_fields.model_dump(),
        "field_validation":          result.field_validation.model_dump(),
        "document_confidence_score": result.document_confidence_score,
        "document_face_extracted":   result.document_face_extracted,
        "document_face_path":        result.document_face_path,
        "aadhaar_qr":                aadhaar_qr,
    })

    logger.info(
        "[%s] Upload complete type=%s confidence=%.4f face_extracted=%s face_path=%s response=%s",
        sid,
        result.document_type,
        result.document_confidence_score,
        result.document_face_extracted,
        result.document_face_path,
        result.model_dump(),
    )
    return result


@router.post(
    "/upload-aadhaar-qr",
    response_model=AadhaarQrResult,
    status_code=status.HTTP_200_OK,
    summary="Upload the side of an Aadhaar card that carries the Secure QR code",
)
async def upload_aadhaar_qr(
    file: UploadFile = File(..., description="JPG / PNG / PDF showing the Aadhaar QR code"),
    session_id: str  = Form(...),
):
    from database.mongodb import verifications_col

    sid = session_id.strip()
    logger.info("[%s] Aadhaar QR upload filename=%s content_type=%s", sid, file.filename, file.content_type)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Allowed: JPG, PNG, PDF",
        )
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 10 MB limit")

    record = await verifications_col().find_one({"session_id": sid}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Session not found. Please upload the document first.")

    try:
        result = await process_aadhaar_qr_upload(
            data,
            file.filename or "aadhaar_qr",
            sid,
            ExtractedFields(**(record.get("extracted_fields") or {})),
            FieldValidation(**(record.get("field_validation") or {})),
        )
    except Exception as exc:
        logger.exception("[%s] Aadhaar QR processing failed", sid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Aadhaar QR processing failed: {str(exc)}",
        ) from exc

    # Keep an earlier successful decode if this upload had no readable QR
    if result.found or not record.get("aadhaar_qr"):
        aadhaar_qr = result.model_dump(mode="json")
        await update_session(sid, {"aadhaar_qr": aadhaar_qr})
        await upsert_verification_fields(sid, {"aadhaar_qr": aadhaar_qr})
    logger.info("[%s] Aadhaar QR upload complete found=%s signature=%s", sid, result.found, result.signature_status)
    return result


@router.get(
    "/document/{session_id}",
    summary="Get document verification result for a session",
)
async def get_document_result(session_id: str):
    from database.mongodb import verifications_col
    col = verifications_col()
    record = await col.find_one({"session_id": session_id}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Session not found")
    return record
