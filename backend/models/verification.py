"""
Pydantic models for request/response and the MongoDB document schema.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


# ── Enums ─────────────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    AADHAAR    = "aadhaar"
    PAN        = "pan"
    PASSPORT   = "passport"
    DRIVING_LICENCE = "driving_licence"
    CITIZENSHIP     = "citizenship"
    EDUCATION       = "education"
    COLLEGE_ID = "college_id"
    UNKNOWN    = "unknown"


class VerificationStatus(str, Enum):
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RejectionReason(str, Enum):
    LOW_DOCUMENT_CONFIDENCE = "Low document confidence score"
    FACE_MISMATCH           = "Face does not match document"
    LIVENESS_FAILED         = "Liveness check failed"
    INVALID_DOCUMENT        = "Document fields could not be validated"
    NO_FACE_FOUND           = "No face detected in document"
    NO_LIVE_FACE            = "No face detected in live capture"
    MULTIPLE_LIVE_FACES     = "More than one face detected in live capture"
    LOW_QUALITY_LIVE_FACE   = "Live face image quality too low — please retake in good lighting, facing the camera"
    FACE_PROCESSING_ERROR   = "Face comparison failed due to a processing error — please retry"
    DOCUMENT_TAMPERED       = "Document appears tampered — it does not match the UIDAI-signed Aadhaar QR code"
    DOCUMENT_INVALID        = "Document failed validation"
    DOCUMENT_SUSPICIOUS     = "Document shows signs of manipulation or inconsistent data"
    PRESENTATION_ATTACK     = "Live capture looks like a screen, print or replay rather than a live person"
    FACE_ALTERED            = "Live capture shows signs of face manipulation or synthesis"
    NONE                    = ""


# ── Sub-models ────────────────────────────────────────────────────────────────

class KycStatus(str, Enum):
    """Final identity decision. VERIFIED requires every required evidence layer to succeed."""
    VERIFIED                 = "VERIFIED"
    REJECTED                 = "REJECTED"
    SUSPICIOUS               = "SUSPICIOUS"
    VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"
    MANUAL_REVIEW_REQUIRED   = "MANUAL_REVIEW_REQUIRED"


class ExtractedFields(BaseModel):
    name:      Optional[str] = None
    dob:       Optional[str] = None
    gender:    Optional[str] = None
    id_number: Optional[str] = None
    address:   Optional[str] = None


class FieldValidation(BaseModel):
    name:      bool = False
    dob:       bool = False
    id_number: bool = False


class QrSignatureStatus(str, Enum):
    VERIFIED   = "verified"    # RSA signature checked against a UIDAI certificate
    INVALID    = "invalid"     # certificates configured, none verifies → forged / edited QR
    UNVERIFIED = "unverified"  # no UIDAI certificate configured on the server
    UNSIGNED   = "unsigned"    # pre-2019 XML QR, which carries no signature


class AadhaarQrResult(BaseModel):
    found:               bool = False
    qr_format:           Optional[str] = None   # secure_v2 | secure_v1 | legacy_xml
    signature_status:    Optional[QrSignatureStatus] = None
    signing_certificate: Optional[str] = None
    # Signed data: name, dob, gender, aadhaar_last4, district, state, pincode
    fields:              dict[str, Optional[str]] = Field(default_factory=dict)
    # field → "match" | "mismatch" | "unavailable", comparing QR data with OCR
    field_checks:        dict[str, str] = Field(default_factory=dict)
    photo_path:          Optional[str] = None
    tamper_flags:        list[str] = Field(default_factory=list)
    message:             str = ""


class AadhaarQrUploadResponse(AadhaarQrResult):
    """QR result plus the recomputed document verification (the QR changes the evidence)."""
    verification: Optional[dict[str, Any]] = None


# ── API Request / Response Models ─────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    session_id:               str
    document_type:            DocumentType
    extracted_fields:         ExtractedFields
    field_validation:         FieldValidation
    document_confidence_score: float = Field(..., ge=0.0, le=1.0)
    document_face_extracted:  bool
    document_face_path:       Optional[str] = None
    aadhaar_qr:               Optional[AadhaarQrResult] = None
    # Unified, evidence-based verification result (see services/kyc/result.py)
    verification:             Optional[dict[str, Any]] = None
    message:                  str


class FaceVerifyRequest(BaseModel):
    session_id:        str
    live_face_base64:  Annotated[str, StringConstraints(max_length=14_000_000)]   # base64-encoded JPEG (~10 MB)
    # Advisory only: the browser's challenge result can make the decision stricter, never looser
    liveness_verified: bool = False
    # Optional short burst of extra frames (base64 JPEG) enabling temporal replay/static-image checks
    extra_frames_base64: list[Annotated[str, StringConstraints(max_length=14_000_000)]] = Field(
        default_factory=list, max_length=8
    )


class FaceVerifyResponse(BaseModel):
    session_id:       str
    verified:         bool
    face_match:       bool
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    liveness_verified: bool
    final_decision:   VerificationStatus
    status:           str
    rejection_reason: Optional[str] = None
    reason:           Optional[str] = None
    message:          str
    # Selfie vs photo in the signed Aadhaar QR, and printed photo vs QR photo
    qr_face_similarity:          Optional[float] = None
    document_qr_face_similarity: Optional[float] = None
    tamper_flags:     list[str] = Field(default_factory=list)
    # ── Unified decision (the authoritative fields; `verified`/`final_decision` are legacy) ──
    kyc_status:       Optional[KycStatus] = None
    face_match_status: Optional[str] = None            # MATCH | NO_MATCH | UNCERTAIN
    liveness:         Optional[dict[str, Any]] = None
    deepfake:         Optional[dict[str, Any]] = None
    risk_score:       Optional[float] = None
    reasons:          list[str] = Field(default_factory=list)
    face_thresholds:  Optional[dict[str, float]] = None


# ── MongoDB Document Schema (stored record) ───────────────────────────────────

class VerificationRecord(BaseModel):
    session_id:                str
    verified:                  bool = False
    status:                    str = "pending"
    document_type:             DocumentType
    extracted_fields:          ExtractedFields
    field_validation:          FieldValidation
    document_confidence_score: float
    document_image_path:       Optional[str] = None
    document_face_path:        Optional[str] = None
    face_match:                Optional[bool] = None
    similarity_score:          Optional[float] = None
    liveness_verified:         Optional[bool] = None
    final_decision:            VerificationStatus = VerificationStatus.PENDING
    rejection_reason:          Optional[str] = None
    reason:                    Optional[str] = None
    created_at:                datetime = Field(default_factory=datetime.utcnow)
    updated_at:                datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump()
        data["document_type"]    = data["document_type"]
        data["final_decision"]   = data["final_decision"]
        return data


# ── Admin / Stats ─────────────────────────────────────────────────────────────

class VerificationStats(BaseModel):
    total:              int = 0
    approved:           int = 0
    rejected:           int = 0
    pending:            int = 0
    approval_rate:      float = 0.0
    avg_similarity:     float = 0.0
