"""
Document verification API routes.
POST /api/upload-document  — upload, OCR, extract fields, extract face
GET  /api/document/{session_id} — fetch session result
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from models.verification import AadhaarQrResult, AadhaarQrUploadResponse, DocumentUploadResponse, ExtractedFields, FieldValidation
from services.document_service import process_aadhaar_qr_upload, process_document
from services.kyc import engine as kyc_engine
from services.kyc.documents import aadhaar as aadhaar_verifier
from services.kyc.result import DocumentVerification, mask_identifier
from services.kyc.user_details import SELECTABLE_DOCUMENT_TYPES, compare_declared_details, parse_declared_type
from utils.uploads import validate_upload
from services.verification_service import (
    create_session,
    generate_session_id,
    update_session,
    upsert_document_record,
    upsert_verification_fields,
)

logger = logging.getLogger(__name__)
router = APIRouter()



def _mask_fields(fields: dict) -> dict:
    """Identifiers are stored masked (last 4 only) — the full number is not needed after the upload."""
    masked = dict(fields)
    masked["id_number"] = mask_identifier(masked.get("id_number"))
    return masked


@router.post(
    "/upload-document",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload identity document for OCR and face extraction",
)
async def upload_document(
    file: UploadFile = File(..., description="JPG / PNG / PDF of identity document"),
    session_id: str  = Form(default=""),
    document_type: str = Form(default="", description="Document type the user selected (required)"),
    full_name: str   = Form(default=""),
    dob:       str   = Form(default=""),
    phone:     str   = Form(default=""),
):
    logger.info(
        "Document upload request filename=%s content_type=%s supplied_session=%s",
        file.filename,
        file.content_type,
        bool(session_id.strip()),
    )
    # ── Validate: size, magic bytes, decodability (client filename/Content-Type are not trusted) ──
    data = await file.read()
    upload = validate_upload(data, file.content_type)
    logger.info("Document upload bytes=%d kind=%s", len(data), upload.extension)

    # ── The user must have chosen a document type (the UI enforces this too) ─────────────────
    declared_type = parse_declared_type(document_type)
    if declared_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please select a document type: " + ", ".join(t.value for t in SELECTABLE_DOCUMENT_TYPES) + ".",
        )

    # ── Session ───────────────────────────────────────────────────────────────
    sid = session_id.strip() or generate_session_id()
    logger.info("[%s] Document upload session initialized", sid)

    # ── Process document pipeline ─────────────────────────────────────────────
    try:
        result, verification = await process_document(data, upload.safe_filename, sid)
    except Exception as exc:
        logger.exception("[%s] Document processing failed", sid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document processing failed. Please try again with a clearer image.",
        ) from exc

    # ── Typed-in name / DOB / document type vs what OCR read (booleans only; nothing is echoed back) ──
    result.declared_document_type = declared_type.value
    result.details_check = compare_declared_details(
        declared_type=declared_type, detected_type=result.document_type,
        full_name=full_name, dob=dob, extracted=result.extracted_fields,
    )
    declared_details = {
        "document_type": declared_type.value,
        "full_name":     full_name.strip(),
        "dob":           dob.strip(),
        "phone":         phone.strip(),
    }

    # ── Persist session + verification record ─────────────────────────────────
    aadhaar_qr = result.aadhaar_qr.model_dump(mode="json") if result.aadhaar_qr else None
    session_data = {
        "document_face_path":        result.document_face_path,
        "document_confidence_score": result.document_confidence_score,
        "document_type":             result.document_type,
        "aadhaar_qr":                aadhaar_qr,
        "document_status":           verification.status.value,
        "document_risk":             verification.risk_score,
        "declared_details":          declared_details,
    }
    await create_session(sid, session_data)
    await upsert_document_record(sid, {
        "document_type":             result.document_type,
        "extracted_fields":          _mask_fields(result.extracted_fields.model_dump()),
        "field_validation":          result.field_validation.model_dump(),
        "document_confidence_score": result.document_confidence_score,
        "document_face_extracted":   result.document_face_extracted,
        "document_face_path":        result.document_face_path,
        "aadhaar_qr":                aadhaar_qr,
        "declared_details":          declared_details,
        "details_check":             result.details_check,
        # Unified evidence-based result (identifiers masked) + server-side audit fields
        "document_verification":     verification.model_dump(mode="json"),
        "document_status":           verification.status.value,
        "verification_provider":     verification.provider,
    })

    logger.info(
        "[%s] Upload complete type=%s status=%s evidence=%s ocr_confidence=%.4f face_extracted=%s",
        sid,
        result.document_type.value,
        verification.status.value,
        verification.evidence_level.value,
        result.document_confidence_score,
        result.document_face_extracted,
    )
    return result


@router.post(
    "/upload-aadhaar-qr",
    response_model=AadhaarQrUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload the side of an Aadhaar card that carries the Secure QR code",
)
async def upload_aadhaar_qr(
    file: UploadFile = File(..., description="JPG / PNG / PDF showing the Aadhaar QR code"),
    session_id: str  = Form(...),
):
    from database.mongodb import verifications_col

    sid = session_id.strip()
    logger.info("[%s] Aadhaar QR upload", sid)
    data = await file.read()
    upload = validate_upload(data, file.content_type)

    record = await verifications_col().find_one({"session_id": sid}, {"_id": 0, "verification_provider": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Session not found. Please upload the document first.")

    try:
        result = await process_aadhaar_qr_upload(
            data,
            upload.safe_filename,
            sid,
            ExtractedFields(**(record.get("extracted_fields") or {})),
            FieldValidation(**(record.get("field_validation") or {})),
        )
    except Exception as exc:
        logger.exception("[%s] Aadhaar QR processing failed", sid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aadhaar QR processing failed. Please try again with a clearer image.",
        ) from exc

    # Keep an earlier successful decode if this upload had no readable QR
    verification_dump = record.get("document_verification")
    if result.found or not record.get("aadhaar_qr"):
        aadhaar_qr = result.model_dump(mode="json")
        record_updates: dict = {"aadhaar_qr": aadhaar_qr}
        session_updates: dict = {"aadhaar_qr": aadhaar_qr}
        if verification_dump:
            # The QR changes the evidence: recompute the document verification from the stored result
            v = DocumentVerification.model_validate(verification_dump)
            aadhaar_verifier.reset_qr(v)
            aadhaar_verifier.apply_qr(v, result)
            kyc_engine.decide(v)
            verification_dump = v.model_dump(mode="json")
            record_updates.update(document_verification=verification_dump, document_status=v.status.value)
            session_updates.update(document_status=v.status.value, document_risk=v.risk_score)
            if result.found:
                record_updates["document_type"] = session_updates["document_type"] = "aadhaar"
        await update_session(sid, session_updates)
        await upsert_verification_fields(sid, record_updates)
    logger.info("[%s] Aadhaar QR upload complete found=%s signature=%s", sid, result.found, result.signature_status)
    return AadhaarQrUploadResponse(**result.model_dump(), verification=verification_dump)


@router.get(
    "/document/{session_id}",
    summary="Get document verification result for a session",
)
async def get_document_result(session_id: str):
    from database.mongodb import verifications_col
    col = verifications_col()
    record = await col.find_one({"session_id": session_id}, {"_id": 0, "verification_provider": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Session not found")
    return record
