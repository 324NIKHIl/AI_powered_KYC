"""
Face verification API routes.
POST /api/face-verify     — compare live webcam face against document face
POST /api/liveness-check  — server-side liveness sanity check only
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from models.verification import FaceVerifyRequest, FaceVerifyResponse
from services.verification_service import run_face_verification

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/face-verify",
    response_model=FaceVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare live face against document face using FaceNet embeddings",
)
async def face_verify(payload: FaceVerifyRequest):
    if not payload.session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required",
        )
    if not payload.live_face_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="live_face_base64 is required",
        )

    logger.info(
        "[%s] Face verify request liveness_verified=%s payload_chars=%d",
        payload.session_id,
        payload.liveness_verified,
        len(payload.live_face_base64),
    )
    try:
        result = await run_face_verification(
            session_id=payload.session_id,
            live_face_b64=payload.live_face_base64,
            liveness_from_frontend=payload.liveness_verified,
            extra_frames_b64=payload.extra_frames_base64,
        )
    except Exception as exc:
        logger.exception("[%s] Face verification failed", payload.session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Face verification failed due to a processing error. Please retry.",
        ) from exc

    logger.info("[%s] Face verify complete kyc_status=%s", payload.session_id, result.kyc_status)
    return result


@router.post(
    "/liveness-check",
    summary="Server-side presentation-attack (liveness) analysis of one or more frames",
)
async def liveness_check(payload: dict):
    """
    Accepts { "frame_base64": "<base64 image>", "extra_frames_base64": [...optional...] }
    Returns { "status": PASS|FAIL|UNCERTAIN, "is_live": bool, "attack_score": float, ... }
    """
    from services.kyc.liveness import LivenessStatus, assess_liveness
    from utils.image_processing import base64_to_numpy

    b64 = payload.get("frame_base64", "")
    if not b64 or not isinstance(b64, str):
        raise HTTPException(status_code=400, detail="frame_base64 is required")
    extras = payload.get("extra_frames_base64") or []
    if not isinstance(extras, list) or len(extras) > 8:
        raise HTTPException(status_code=400, detail="extra_frames_base64 must be a list of at most 8 frames")
    try:
        img = base64_to_numpy(b64)
        extra_imgs = [base64_to_numpy(e) for e in extras if isinstance(e, str)]
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode the image")
    try:
        result = assess_liveness(img, None, extra_imgs)
    except Exception:
        logger.exception("Liveness check failed")
        raise HTTPException(status_code=500, detail="Liveness check failed")
    return {**result.to_dict(), "is_live": result.status == LivenessStatus.PASS}
