"""
Verification Service — orchestrates face verification and final decision logic,
then persists the result to MongoDB.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from models.verification import (
    FaceVerifyResponse,
    KycStatus,
    QrSignatureStatus,
    RejectionReason,
    VerificationStatus,
)
from services.face_service import (
    SIMILARITY_THRESHOLD,
    cosine_similarity,
    reference_embedding,
    verify_faces,
)
from services.kyc.config import face_match_threshold, face_no_match_threshold
from services.kyc.deepfake import assess_face_alteration
from services.kyc.identity import FaceMatch, classify_similarity, decide_identity
from services.kyc.liveness import LivenessStatus, assess_liveness
from database.mongodb import sessions_col, verifications_col
from utils.image_processing import base64_to_numpy, save_image

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


async def update_session(session_id: str, updates: dict) -> None:
    await sessions_col().update_one({"session_id": session_id}, {"$set": updates})


async def upsert_verification_fields(session_id: str, updates: dict) -> None:
    await verifications_col().update_one(
        {"session_id": session_id},
        {"$set": {**updates, "updated_at": datetime.now(timezone.utc)}},
    )


async def get_session(session_id: str) -> Optional[dict]:
    col = sessions_col()
    return await col.find_one({"session_id": session_id}, {"_id": 0})


# ── Face verification + decision pipeline ─────────────────────────────────────

async def run_face_verification(
    session_id: str,
    live_face_b64: str,
    liveness_from_frontend: bool,
    extra_frames_b64: Optional[list[str]] = None,
) -> FaceVerifyResponse:
    """
    Document verification (already done at upload) → live capture → liveness → face detection
    → embedding → comparison → alteration analysis → final identity decision.

    Everything is decided here, on the backend. The browser's liveness flag is advisory: it can
    tighten the decision but never loosen it.
    """
    started = time.perf_counter()
    logger.info("[%s] Face verification started frames=%d", session_id, 1 + len(extra_frames_b64 or []))
    session = await get_session(session_id)
    if not session:
        logger.warning("[%s] Session not found during face verification", session_id)
        return _face_response(
            session_id=session_id, verified=False, similarity=0.0, liveness=False,
            decision=VerificationStatus.REJECTED,
            reason="Session not found. Please upload a document first.",
        )

    doc_face_path: Optional[str] = session.get("document_face_path")
    document_status: Optional[str] = session.get("document_status")
    document_risk = float(session.get("document_risk", 0.0) or 0.0)

    try:
        live_img = base64_to_numpy(live_face_b64)
    except Exception:
        logger.error("[%s] Live face decode failed", session_id)
        return _rejected_response(session_id, RejectionReason.NO_LIVE_FACE)
    extra_frames = []
    for b64 in (extra_frames_b64 or [])[:8]:
        try:
            extra_frames.append(base64_to_numpy(b64))
        except Exception:
            continue   # an undecodable extra frame only reduces the temporal evidence

    # ── Aadhaar Secure QR (optional) ──────────────────────────────────────────
    # The photo inside the QR is only trusted when its signature verified, or
    # when it couldn't be checked for lack of a certificate (still decoded QR data).
    qr: dict = session.get("aadhaar_qr") or {}
    qr_photo_path: Optional[str] = None
    if qr.get("signature_status") in (QrSignatureStatus.VERIFIED.value, QrSignatureStatus.UNVERIFIED.value):
        qr_photo_path = qr.get("photo_path")

    # Printed photo is the primary reference; the QR photo stands in if none was found
    reference_path = doc_face_path or qr_photo_path

    # ── Face detection, alignment, embedding, comparison ──────────────────────
    capture_issue: Optional[str] = None
    face_status: Optional[str] = None
    similarity = 0.0
    live_face_path: Optional[str] = None
    live_embedding = None
    face_box = None
    match_reason: Optional[RejectionReason] = None

    if not reference_path:
        logger.warning("[%s] No reference face for this session", session_id)
        capture_issue = RejectionReason.NO_FACE_FOUND.value
    else:
        match = verify_faces(reference_path, live_img)
        similarity, live_embedding, face_box = match.similarity, match.live_embedding, match.live_face_box
        match_reason = match.rejection_reason
        if match.live_face_crop is not None:
            live_face_path = save_image(match.live_face_crop, "uploads/faces", prefix=f"live_{session_id}")
        if match.aligned_pair is not None:
            save_image(match.aligned_pair, "uploads/faces", prefix=f"pair_{session_id}")
        if match_reason in (None, RejectionReason.FACE_MISMATCH):
            face_status = classify_similarity(similarity)
        else:
            capture_issue = match_reason.value   # no/multiple faces, poor quality, processing error → retake
        logger.info("[%s] Face status=%s similarity=%.4f", session_id, face_status, similarity)

    tamper_flags: list[str] = list(qr.get("tamper_flags") or [])
    qr_face_similarity, document_qr_face_similarity = _compare_with_qr_photo(
        session_id, qr_photo_path, doc_face_path, live_embedding, tamper_flags
    )
    # The signed QR photo disagreeing with the selfie while the printed photo agrees = inconclusive
    if (face_status == FaceMatch.MATCH and qr_face_similarity is not None
            and classify_similarity(qr_face_similarity) == FaceMatch.NO_MATCH):
        face_status = FaceMatch.UNCERTAIN

    # ── Liveness + face-alteration (server-side; run even if the match failed, for the audit trail) ──
    liveness = assess_liveness(live_img, face_box, extra_frames, client_challenge_passed=liveness_from_frontend)
    deepfake = assess_face_alteration(live_img, face_box)

    # ── Final identity decision ───────────────────────────────────────────────
    decision = decide_identity(
        document_status=document_status,
        document_risk=document_risk,
        face_status=face_status,
        capture_issue=capture_issue,
        liveness=liveness,
        deepfake=deepfake,
        extra_tamper_flags=[f for f in tamper_flags if "signature is invalid" not in f],
        similarity=similarity,
    )
    kyc_status = decision.status
    legacy = decision.legacy_decision
    verified = kyc_status == KycStatus.VERIFIED
    reason_text = "; ".join(decision.reasons) if decision.reasons else None
    status_text = {VerificationStatus.APPROVED: "approved", VerificationStatus.REJECTED: "rejected"}.get(legacy, "pending")
    thresholds = {"face_match": face_match_threshold(), "face_no_match": face_no_match_threshold()}
    logger.info(
        "[%s] Final decision=%s doc=%s face=%s liveness=%s deepfake=%s risk=%.3f ms=%d",
        session_id, kyc_status.value, document_status, face_status, liveness.status.value,
        deepfake.level, decision.risk_score, int((time.perf_counter() - started) * 1000),
    )

    await _upsert_verification(session_id, session, {
        "verified":          verified,
        "face_match":        face_status == FaceMatch.MATCH,
        "face_match_status": face_status,
        "similarity_score":  round(similarity, 4),
        "liveness_verified": liveness.status == LivenessStatus.PASS,
        "liveness":          liveness.to_dict(),
        "deepfake":          deepfake.to_dict(),
        "kyc_status":        kyc_status.value,
        "risk_score":        decision.risk_score,
        "reasons":           decision.reasons,
        "final_decision":    legacy,
        "status":            status_text,
        "rejection_reason":  reason_text,
        "reason":            reason_text,
        "live_face_path":    live_face_path,
        "qr_face_similarity":          qr_face_similarity,
        "document_qr_face_similarity": document_qr_face_similarity,
        "tamper_flags":      tamper_flags,
        "face_thresholds":   thresholds,
        "verified_at":       datetime.now(timezone.utc),
        "updated_at":        datetime.now(timezone.utc),
    })

    return FaceVerifyResponse(
        session_id=session_id,
        verified=verified,
        face_match=face_status == FaceMatch.MATCH,
        similarity_score=round(max(0.0, min(1.0, similarity)), 4),
        liveness_verified=liveness.status == LivenessStatus.PASS,
        final_decision=legacy,
        status=status_text,
        rejection_reason=reason_text,
        reason=reason_text,
        message=f"Verification {kyc_status.value}" + (f" — {reason_text}" if reason_text else ""),
        qr_face_similarity=qr_face_similarity,
        document_qr_face_similarity=document_qr_face_similarity,
        tamper_flags=tamper_flags,
        kyc_status=kyc_status,
        face_match_status=face_status,
        liveness=liveness.to_dict(),
        deepfake=deepfake.to_dict(),
        risk_score=decision.risk_score,
        reasons=decision.reasons,
        face_thresholds=thresholds,
    )


def _compare_with_qr_photo(
    session_id: str,
    qr_photo_path: Optional[str],
    doc_face_path: Optional[str],
    live_embedding,
    tamper_flags: list[str],
) -> tuple[Optional[float], Optional[float]]:
    """
    Compare the selfie and the printed photo against the photo inside the Aadhaar QR.
    Both photos come from the same enrolment, so a printed photo that doesn't match
    the QR photo means it was substituted. Appends to tamper_flags in that case.
    Returns (selfie↔QR, printed↔QR) similarities.
    """
    if not qr_photo_path:
        return None, None
    try:
        qr_embedding = reference_embedding(qr_photo_path)
        if qr_embedding is None:
            logger.warning("[%s] No face detected in Aadhaar QR photo %s", session_id, qr_photo_path)
            return None, None

        selfie_qr = None
        if live_embedding is not None:
            selfie_qr = round(max(0.0, cosine_similarity(live_embedding, qr_embedding)), 4)

        printed_qr = None
        doc_embedding = reference_embedding(doc_face_path) if doc_face_path else None
        if doc_embedding is not None:
            printed_qr = round(max(0.0, cosine_similarity(doc_embedding, qr_embedding)), 4)
            if printed_qr < SIMILARITY_THRESHOLD:
                tamper_flags.append("Photo printed on the card does not match the photo in the Aadhaar QR code")

        logger.info("[%s] QR photo similarity selfie=%s printed=%s", session_id, selfie_qr, printed_qr)
        return selfie_qr, printed_qr
    except Exception:
        logger.exception("[%s] Aadhaar QR photo comparison failed", session_id)
        return None, None


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
