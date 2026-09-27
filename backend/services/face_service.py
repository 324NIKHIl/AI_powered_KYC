"""
Face Verification Service for KYC

Pipeline:
1. Detect faces with MTCNN (largest face on the document; exactly one face in the live frame)
2. Quality gate on the live face (size, pose, blur, brightness)
3. Align both faces onto the ArcFace 5-point landmark template (112×112)
4. ArcFace embeddings with horizontal-flip test-time augmentation
5. Cosine similarity against a threshold

Alignment is the critical step: ArcFace is trained on landmark-aligned crops, and
feeding it loose, unaligned crops (as the previous version did via
detector_backend="skip") produces embeddings dominated by pose/background, which
lets different people clear the threshold and the same person miss it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from models.verification import RejectionReason
from utils.image_processing import align_face, crop_face, detect_faces

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# Raw cosine similarity between aligned, flip-augmented ArcFace embeddings.
SIMILARITY_THRESHOLD = float(
    os.getenv(
        "FACE_SIMILARITY_THRESHOLD",
        os.getenv("FACE_MATCH_THRESHOLD", "0.40"),
    )
)

FACE_MODEL = os.getenv("FACE_MODEL", "ArcFace")

# Document photos are printed / re-photographed, so MTCNN is less confident on them.
DOCUMENT_FACE_MIN_CONFIDENCE = 0.80
LIVE_FACE_MIN_CONFIDENCE = 0.90

# Another face at least this fraction of the main face's area counts as a second person.
SECOND_FACE_AREA_RATIO = 0.20

# Live-face quality gates
MIN_EYE_DISTANCE_PX = float(os.getenv("FACE_MIN_EYE_DISTANCE_PX", "30"))
MAX_YAW_RATIO = 0.35  # |nose offset from eye midpoint| / eye distance
MIN_BLUR_SCORE = 20.0
MIN_BRIGHTNESS = 40.0
MAX_BRIGHTNESS = 220.0


@dataclass
class FaceMatchResult:
    verified: bool
    similarity: float
    rejection_reason: Optional[RejectionReason] = None
    live_face_crop: Optional[np.ndarray] = None


# ============================================================
# FACE QUALITY CHECKS
# ============================================================

def check_face_quality(aligned: np.ndarray, keypoints: dict) -> Tuple[bool, str]:
    """Quality gate on a live face: size, frontal pose, sharpness, exposure."""
    left_eye = np.array(keypoints["left_eye"], dtype=np.float64)
    right_eye = np.array(keypoints["right_eye"], dtype=np.float64)
    nose = np.array(keypoints["nose"], dtype=np.float64)

    eye_distance = float(np.linalg.norm(right_eye - left_eye))
    if eye_distance < MIN_EYE_DISTANCE_PX:
        return False, f"face too small (eye distance {eye_distance:.0f}px)"

    yaw_ratio = abs(nose[0] - (left_eye[0] + right_eye[0]) / 2) / eye_distance
    if yaw_ratio > MAX_YAW_RATIO:
        return False, f"face not frontal (yaw ratio {yaw_ratio:.2f})"

    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_score < MIN_BLUR_SCORE:
        return False, f"too blurry (score {blur_score:.1f})"

    brightness = float(np.mean(gray))
    if brightness < MIN_BRIGHTNESS:
        return False, f"too dark (brightness {brightness:.0f})"
    if brightness > MAX_BRIGHTNESS:
        return False, f"too bright (brightness {brightness:.0f})"

    return True, "good quality"

# ============================================================
# LIVENESS CHECK
# ============================================================

def check_liveness(img: np.ndarray) -> Tuple[bool, float]:
    """
    Basic liveness estimation.
    """

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Texture variation
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Edge density
    edges = cv2.Canny(gray, 100, 200)
    edge_density = np.mean(edges)

    score = (
        min(laplacian_var / 150.0, 1.0) * 0.7
        + min(edge_density / 25.0, 1.0) * 0.3
    )

    is_live = score > 0.30  # Reduced from 0.45 to be less strict

    logger.info(
        "Liveness score=%.4f live=%s",
        score,
        is_live
    )

    return is_live, float(score)

# ============================================================
# EMBEDDING
# ============================================================

_model = None


def _get_model():
    global _model
    if _model is None:
        from deepface import DeepFace
        _model = DeepFace.build_model(FACE_MODEL)
    return _model


def generate_embedding(aligned: np.ndarray) -> np.ndarray:
    """
    ArcFace embedding of an aligned 112×112 BGR face.
    Input is BGR scaled to [0, 1], matching what DeepFace.represent feeds the
    model on its standard (detector) path.
    The embeddings of the face and its mirror image are L2-normalised and
    summed, which makes the result robust to the mirrored webcam capture.
    """
    model = _get_model()
    width, height = getattr(model, "input_shape", (112, 112))
    face = aligned if aligned.shape[:2] == (height, width) else cv2.resize(aligned, (width, height))
    batch = np.stack([face, cv2.flip(face, 1)]).astype(np.float32) / 255.0
    keras_model = getattr(model, "model", model)
    embeddings = np.asarray(keras_model(batch, training=False), dtype=np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    combined = embeddings.sum(axis=0)
    return combined / np.linalg.norm(combined)

# ============================================================
# COSINE SIMILARITY
# ============================================================

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute raw cosine similarity between two embeddings."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))

# ============================================================
# MAIN VERIFICATION
# ============================================================

def verify_faces(document_face_path: str, live_img: np.ndarray) -> FaceMatchResult:
    """
    Compare the face on the document against the live webcam frame.
    `live_img` is the full frame (not a crop) so that extra faces can be detected.
    """
    try:
        # ── Document face ────────────────────────────────────────────────────
        doc_img = cv2.imread(document_face_path)
        if doc_img is None:
            logger.warning("Document face could not be read: %s", document_face_path)
            return FaceMatchResult(False, 0.0, RejectionReason.NO_FACE_FOUND)

        doc_faces = detect_faces(doc_img, min_confidence=DOCUMENT_FACE_MIN_CONFIDENCE)
        if not doc_faces:
            logger.warning("No alignable face in document crop %s", document_face_path)
            return FaceMatchResult(False, 0.0, RejectionReason.NO_FACE_FOUND)
        doc_face = doc_faces[0]

        # ── Live face ────────────────────────────────────────────────────────
        live_faces = detect_faces(live_img, min_confidence=LIVE_FACE_MIN_CONFIDENCE)
        if not live_faces:
            logger.warning("No face detected in live frame shape=%s", live_img.shape)
            return FaceMatchResult(False, 0.0, RejectionReason.NO_LIVE_FACE)
        live_face = live_faces[0]
        live_crop = crop_face(live_img, live_face["box"])

        main_area = live_face["box"][2] * live_face["box"][3]
        others = [f for f in live_faces[1:] if f["box"][2] * f["box"][3] >= SECOND_FACE_AREA_RATIO * main_area]
        if others:
            logger.warning("Live frame contains %d faces", 1 + len(others))
            return FaceMatchResult(False, 0.0, RejectionReason.MULTIPLE_LIVE_FACES, live_crop)

        # ── Alignment + quality ──────────────────────────────────────────────
        doc_aligned = align_face(doc_img, doc_face["keypoints"])
        live_aligned = align_face(live_img, live_face["keypoints"])

        quality_ok, quality_reason = check_face_quality(live_aligned, live_face["keypoints"])
        if not quality_ok:
            logger.warning("Live face quality rejected: %s", quality_reason)
            return FaceMatchResult(False, 0.0, RejectionReason.LOW_QUALITY_LIVE_FACE, live_crop)

        # ── Embeddings + similarity ──────────────────────────────────────────
        similarity = cosine_similarity(generate_embedding(doc_aligned), generate_embedding(live_aligned))
        verified = similarity >= SIMILARITY_THRESHOLD

        logger.info(
            "Face similarity=%.4f threshold=%.4f model=%s verified=%s doc_conf=%.3f live_conf=%.3f",
            similarity,
            SIMILARITY_THRESHOLD,
            FACE_MODEL,
            verified,
            doc_face["confidence"],
            live_face["confidence"],
        )

        return FaceMatchResult(
            verified=verified,
            similarity=max(0.0, min(1.0, similarity)),
            rejection_reason=None if verified else RejectionReason.FACE_MISMATCH,
            live_face_crop=live_crop,
        )

    except Exception:
        logger.exception("Verification failed")
        return FaceMatchResult(False, 0.0, RejectionReason.FACE_MISMATCH)
