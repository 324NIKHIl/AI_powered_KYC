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
        )
    except Exception as exc:
        logger.exception("[%s] Face verification failed", payload.session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Face verification failed: {str(exc)}",
        ) from exc

    logger.info("[%s] Face verify response=%s", payload.session_id, result.model_dump())
    return result


@router.post(
    "/liveness-check",
    summary="Quick server-side liveness check (gradient analysis)",
)
async def liveness_check(payload: dict):
    """
    Accepts { "frame_base64": "<base64 image>" }
    Returns { "is_live": bool, "confidence": float }
    """
    from utils.image_processing import base64_to_numpy
    from services.face_service import check_liveness

    b64 = payload.get("frame_base64", "")
    if not b64:
        raise HTTPException(status_code=400, detail="frame_base64 is required")
    try:
        img = base64_to_numpy(b64)
        is_live, confidence = check_liveness(img)
        logger.info("Liveness API result live=%s confidence=%.4f shape=%s", is_live, confidence, img.shape)
        return {"is_live": is_live, "confidence": round(confidence, 4)}
    except Exception as exc:
        logger.exception("Liveness check failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
