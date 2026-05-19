"""
Pydantic models for request/response and the MongoDB document schema.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    AADHAAR    = "aadhaar"
    PAN        = "pan"
    PASSPORT   = "passport"
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
    NONE                    = ""


# ── Sub-models ────────────────────────────────────────────────────────────────

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


# ── API Request / Response Models ─────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    session_id:               str
    document_type:            DocumentType
    extracted_fields:         ExtractedFields
    field_validation:         FieldValidation
    document_confidence_score: float = Field(..., ge=0.0, le=1.0)
    document_face_extracted:  bool
    document_face_path:       Optional[str] = None
    message:                  str


class FaceVerifyRequest(BaseModel):
    session_id:        str
    live_face_base64:  str   # base64-encoded JPEG
    liveness_verified: bool = False


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
