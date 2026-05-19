"""
Verification Service — orchestrates face verification and final decision logic,
then persists the result to MongoDB.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from models.verification import (
    FaceVerifyResponse,
    RejectionReason,
    VerificationStatus,
)
from services.face_service import check_liveness, verify_faces
from database.mongodb import sessions_col, verifications_col
from utils.image_processing import base64_to_numpy, extract_face_mtcnn, save_image

logger = logging.getLogger(__name__)

# Thresholds
import os
DOCUMENT_CONFIDENCE_THRESHOLD = float(os.getenv("DOCUMENT_CONFIDENCE_THRESHOLD", "0.75"))
REQUIRE_DOCUMENT_CONFIDENCE_FOR_APPROVAL = (
    os.getenv("REQUIRE_DOCUMENT_CONFIDENCE_FOR_APPROVAL", "false").lower() == "true"
)


# ── Session helpers ───────────────────────────────────────────────────────────

def generate_session_id() -> str:
    return uuid.uuid4().hex


async def create_session(session_id: str, extra: dict) -> None:
    """Upsert a lightweight session document so we can look up doc_face_path later."""
    col = sessions_col()
    await col.update_one(
        {"session_id": session_id},
        {"$set": {**extra, "session_id": session_id, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def get_session(session_id: str) -> Optional[dict]:
    col = sessions_col()
    return await col.find_one({"session_id": session_id}, {"_id": 0})


# ── Face verification + decision pipeline ─────────────────────────────────────

async def run_face_verification(
    session_id: str,
    live_face_b64: str,
    liveness_from_frontend: bool,
) -> FaceVerifyResponse:
    """
    Full pipeline:
    1. Decode live face from base64
    2. Server-side liveness check
    3. Compare against document face
    4. Make APPROVED / REJECTED decision
    5. Persist to MongoDB
    """
    # ── Load session ──────────────────────────────────────────────────────────
    logger.info(
        "[%s] Face verification started frontend_liveness=%s",
        session_id,
        liveness_from_frontend,
    )
    session = await get_session(session_id)
    if not session:
        logger.warning("[%s] Session not found during face verification", session_id)
        return _face_response(
            session_id=session_id,
            verified=False,
            similarity=0.0,
            liveness=False,
            decision=VerificationStatus.REJECTED,
            reason="Session not found. Please upload a document first.",
        )

    doc_face_path: Optional[str] = session.get("document_face_path")
    doc_confidence: float = float(session.get("document_confidence_score", 0.0))
    logger.info(
        "[%s] Session loaded doc_face_path=%s doc_confidence=%.4f doc_threshold=%.4f require_doc_confidence=%s",
        session_id,
        doc_face_path,
        doc_confidence,
        DOCUMENT_CONFIDENCE_THRESHOLD,
        REQUIRE_DOCUMENT_CONFIDENCE_FOR_APPROVAL,
    )

    # ── Decode live face ──────────────────────────────────────────────────────
    try:
        live_img = base64_to_numpy(live_face_b64)
    except Exception as exc:
        logger.error("[%s] Live face decode failed: %s", session_id, exc)
        return _rejected_response(session_id, RejectionReason.NO_LIVE_FACE)
    logger.info("[%s] Live image decoded shape=%s", session_id, live_img.shape)

    # ── Server-side liveness ──────────────────────────────────────────────────
    server_live, liveness_score = check_liveness(live_img)
    liveness_ok = liveness_from_frontend or server_live
    logger.info(
        "[%s] Liveness frontend=%s server=%s score=%.4f final=%s",
        session_id,
        liveness_from_frontend,
        server_live,
        liveness_score,
        liveness_ok,
    )
    if not liveness_ok:
        logger.warning(
            "[%s] Liveness not confirmed (frontend=%s server=%s); continuing face comparison",
            session_id, liveness_from_frontend, server_live
        )

    # ── Detect and save live face crop ────────────────────────────────────────
    live_face_img = extract_face_mtcnn(live_img)
    if live_face_img is None:
        logger.warning("[%s] No face detected in live capture", session_id)
        await _save_rejected_record(session_id, session, 0.0, liveness_ok, RejectionReason.NO_LIVE_FACE)
        return _rejected_response(session_id, RejectionReason.NO_LIVE_FACE, liveness=liveness_ok)
    logger.info("[%s] Live face crop shape=%s", session_id, live_face_img.shape)

    live_face_path = save_image(live_face_img, "uploads/faces", prefix=f"live_{session_id}")
    logger.info("[%s] Live face saved: %s", session_id, live_face_path)

    # ── Face comparison ────────────────────────────────────────────────────────
    if not doc_face_path:
        logger.warning("[%s] No document face path in session", session_id)
        await _save_rejected_record(session_id, session, 0.0, liveness_ok, RejectionReason.NO_FACE_FOUND)
        return _rejected_response(session_id, RejectionReason.NO_FACE_FOUND, liveness=liveness_ok)

    face_match, similarity = verify_faces(doc_face_path, live_face_img)
    logger.info("[%s] Similarity: %.4f", session_id, similarity)
    logger.info("[%s] Verified: %s", session_id, face_match)

    # ── Final decision ────────────────────────────────────────────────────────
    rejection_reason: Optional[RejectionReason] = None
    if not face_match:
        rejection_reason = RejectionReason.FACE_MISMATCH
    elif not liveness_ok:
        rejection_reason = RejectionReason.LIVENESS_FAILED
    elif REQUIRE_DOCUMENT_CONFIDENCE_FOR_APPROVAL and doc_confidence < DOCUMENT_CONFIDENCE_THRESHOLD:
        rejection_reason = RejectionReason.LOW_DOCUMENT_CONFIDENCE
    elif doc_confidence < DOCUMENT_CONFIDENCE_THRESHOLD:
        logger.warning(
            "[%s] Document confidence %.4f is below threshold %.4f, but not blocking approval",
            session_id,
            doc_confidence,
            DOCUMENT_CONFIDENCE_THRESHOLD,
        )

    decision = VerificationStatus.APPROVED if rejection_reason is None else VerificationStatus.REJECTED
    verified = decision == VerificationStatus.APPROVED
    reason_text = rejection_reason.value if rejection_reason else None
    status_text = "approved" if verified else "rejected"
    logger.info(
        "[%s] Final decision=%s verified=%s reason=%s similarity=%.4f liveness=%s",
        session_id,
        decision.value,
        verified,
        reason_text,
        similarity,
        liveness_ok,
    )

    # ── Persist ───────────────────────────────────────────────────────────────
    await _upsert_verification(session_id, session, {
        "verified":         verified,
        "face_match":       face_match,
        "similarity_score": round(similarity, 4),
        "liveness_verified": liveness_ok,
        "final_decision":   decision,
        "status":           status_text,
        "rejection_reason": reason_text,
        "reason":           reason_text,
        "live_face_path":   live_face_path,
        "updated_at":       datetime.now(timezone.utc),
    })

    response = FaceVerifyResponse(
        session_id=session_id,
        verified=verified,
        face_match=face_match,
        similarity_score=round(similarity, 4),
        liveness_verified=liveness_ok,
        final_decision=decision,
        status=status_text,
        rejection_reason=reason_text,
        reason=reason_text,
        message=f"Verification {decision.value}" + (f" — {reason_text}" if reason_text else ""),
    )
    logger.info("[%s] Face verify API response=%s", session_id, response.model_dump())
    return response


# ── DB helpers ────────────────────────────────────────────────────────────────

async def upsert_document_record(session_id: str, doc_data: dict) -> None:
    """Create / update the verification record after document upload."""
    col = verifications_col()
    await col.update_one(
        {"session_id": session_id},
        {
            "$set": {
                **doc_data,
                "session_id":  session_id,
                "final_decision": VerificationStatus.PENDING,
                "status":      "pending",
                "verified":    False,
                "created_at":  datetime.now(timezone.utc),
                "updated_at":  datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def _upsert_verification(session_id: str, session: dict, updates: dict) -> None:
    col = verifications_col()
    await col.update_one(
        {"session_id": session_id},
        {"$set": updates},
        upsert=True,
    )


async def _save_rejected_record(
    session_id: str,
    session: dict,
    similarity: float,
    liveness: bool,
    reason: RejectionReason,
) -> None:
    await _upsert_verification(session_id, session, {
        "verified":         False,
        "face_match":       False,
        "similarity_score": similarity,
        "liveness_verified": liveness,
        "final_decision":   VerificationStatus.REJECTED,
        "status":           "rejected",
        "rejection_reason": reason.value,
        "reason":           reason.value,
        "updated_at":       datetime.now(timezone.utc),
    })


def _face_response(
    session_id: str,
    verified: bool,
    similarity: float,
    liveness: bool,
    decision: VerificationStatus,
    reason: Optional[str],
) -> FaceVerifyResponse:
    status_text = "approved" if verified else "rejected"
    return FaceVerifyResponse(
        session_id=session_id,
        verified=verified,
        face_match=False,
        similarity_score=round(similarity, 4),
        liveness_verified=liveness,
        final_decision=decision,
        status=status_text,
        rejection_reason=reason,
        reason=reason,
        message=f"Verification {decision.value}" + (f" — {reason}" if reason else ""),
    )


def _rejected_response(
    session_id: str,
    reason: RejectionReason,
    *,
    similarity: float = 0.0,
    liveness: bool = False,
) -> FaceVerifyResponse:
    return _face_response(
        session_id=session_id,
        verified=False,
        similarity=similarity,
        liveness=liveness,
        decision=VerificationStatus.REJECTED,
        reason=reason.value,
    )
