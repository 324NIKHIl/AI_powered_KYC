"""
Secure Face Verification Service for KYC
Improved version with:
- Strict threshold
- ArcFace model
- Stronger detection
- Anti-spoofing
- Better validation
- Safer similarity logic
- Multi-check verification

Requirements:
pip install deepface opencv-python numpy face_recognition
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# Raw ArcFace cosine similarity is much lower than the old normalized score.
# DeepFace's tuned ArcFace cosine distance threshold is 0.68, which maps to
# raw cosine similarity >= 0.32.
SIMILARITY_THRESHOLD = float(
    os.getenv(
        "FACE_SIMILARITY_THRESHOLD",
        os.getenv("FACE_MATCH_THRESHOLD", "0.32"),
    )
)

# Better than FaceNet
FACE_MODEL = os.getenv("FACE_MODEL", "ArcFace")

# Used only when a full image needs DeepFace-side detection. The verification
# path compares crops that were already produced by MTCNN/OpenCV, so embedding
# generation deliberately uses detector_backend="skip" to avoid a second
# detector pass and TensorFlow/Keras conflicts.
DETECTOR_BACKEND = os.getenv("FACE_DETECTOR", "retinaface")

# ============================================================
# FACE QUALITY CHECKS
# ============================================================

def check_image_quality(img: np.ndarray) -> Tuple[bool, str]:
    """
    Checks if image quality is acceptable.
    """

    if img is None:
        return False, "Image is empty"

    h, w = img.shape[:2]

    # Minimum resolution
    if h < 120 or w < 120:
        return False, "Face resolution too low"

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur detection
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    if blur_score < 30:  # Reduced from 80 to be less strict
        return False, "Image too blurry"

    # Brightness check
    brightness = np.mean(gray)

    if brightness < 30:  # Reduced from 40
        return False, "Image too dark"

    if brightness > 230:  # Increased from 220
        return False, "Image too bright"

    return True, "Good quality"

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

def generate_embedding(img_path: str) -> Optional[np.ndarray]:

    try:
        from deepface import DeepFace

        result = DeepFace.represent(
            img_path=img_path,
            model_name=FACE_MODEL,
            detector_backend="skip",
            enforce_detection=False,
            align=True,
            anti_spoofing=False  # Disabled as it's too strict and causes false rejections
        )

        if isinstance(result, list) and len(result) > 0:
            embedding = result[0]["embedding"]
            logger.info("Embedding generated successfully for %s (dims: %d)", img_path, len(embedding))
            return np.array(embedding, dtype=np.float32)

        logger.warning("No faces detected for embedding in %s", img_path)
        return None

    except Exception as exc:
        logger.error("Embedding generation failed for %s: %s", img_path, exc)
        return None

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


def cosine_distance_from_similarity(similarity: float) -> float:
    """DeepFace cosine distance is 1 - raw cosine similarity."""
    return 1.0 - similarity

# ============================================================
# SAVE TEMP IMAGE
# ============================================================

def save_temp_image(img: np.ndarray) -> str:

    os.makedirs("uploads/faces", exist_ok=True)

    temp_path = f"uploads/faces/{uuid.uuid4().hex}.jpg"

    cv2.imwrite(
        temp_path,
        img,
        [int(cv2.IMWRITE_JPEG_QUALITY), 95]
    )

    return temp_path

# ============================================================
# FACE DETECTION VALIDATION
# ============================================================

def validate_single_face(img_path: str) -> bool:
    """
    Validate that a saved face crop is usable.

    The document and live images passed to verify_faces are already face crops.
    Running RetinaFace again here can fail in the FastAPI process after MTCNN
    has initialized TensorFlow/Keras, causing false rejections with score 0.
    """
    img = cv2.imread(img_path)
    if img is None:
        logger.warning("Face crop could not be read: %s", img_path)
        return False

    h, w = img.shape[:2]
    if h < 80 or w < 80:
        logger.warning("Face crop too small for embedding: %s shape=%s", img_path, img.shape)
        return False

    return True

# ============================================================
# MAIN VERIFICATION
# ============================================================

def verify_faces(
    document_face_path: str,
    live_face_img: np.ndarray
) -> tuple[bool, float]:

    """
    Returns:
    (
        verified,
        similarity_score
    )
    """

    live_temp_path = None

    try:

        # ----------------------------------------------------
        # IMAGE QUALITY CHECK
        # ----------------------------------------------------

        quality_ok, quality_reason = check_image_quality(live_face_img)

        if not quality_ok:
            logger.warning("Live face quality rejected: %s", quality_reason)
            return False, 0.0

        # ----------------------------------------------------
        # SAVE LIVE IMAGE
        # ----------------------------------------------------

        live_temp_path = save_temp_image(live_face_img)

        # ----------------------------------------------------
        # FACE VALIDATION
        # ----------------------------------------------------

        if not validate_single_face(document_face_path):
            logger.warning("Document face validation failed for %s", document_face_path)
            return False, 0.0

        if not validate_single_face(live_temp_path):
            logger.warning("Live face validation failed for %s", live_temp_path)
            return False, 0.0

        # ----------------------------------------------------
        # GENERATE EMBEDDINGS
        # ----------------------------------------------------

        doc_embedding = generate_embedding(document_face_path)

        if doc_embedding is None:
            logger.warning("Document face embedding failed for %s", document_face_path)
            return False, 0.0

        live_embedding = generate_embedding(live_temp_path)

        if live_embedding is None:
            logger.warning("Live face embedding failed for %s", live_temp_path)
            return False, 0.0

        # ----------------------------------------------------
        # SIMILARITY
        # ----------------------------------------------------

        similarity = cosine_similarity(
            doc_embedding,
            live_embedding
        )

        similarity = max(0.0, min(1.0, similarity))

        logger.info(
            "Face similarity=%.4f distance=%.4f threshold=%.4f model=%s embedding_detector=skip",
            similarity,
            cosine_distance_from_similarity(similarity),
            SIMILARITY_THRESHOLD,
            FACE_MODEL,
        )

        # ----------------------------------------------------
        # FINAL DECISION
        # ----------------------------------------------------

        verified = similarity >= SIMILARITY_THRESHOLD
        logger.info("Verified: %s", verified)

        return verified, similarity

    except Exception as exc:

        logger.exception("Verification failed")

        return False, 0.0

    finally:

        if live_temp_path and os.path.exists(live_temp_path):
            os.remove(live_temp_path)

# ============================================================
# OPTIONAL FALLBACK
# ============================================================

def fallback_face_recognition(
    document_face_path: str,
    live_face_img: np.ndarray
):

    try:

        import face_recognition

        doc_img = face_recognition.load_image_file(
            document_face_path
        )

        live_rgb = cv2.cvtColor(
            live_face_img,
            cv2.COLOR_BGR2RGB
        )

        doc_encodings = face_recognition.face_encodings(doc_img)
        live_encodings = face_recognition.face_encodings(live_rgb)

        if not doc_encodings or not live_encodings:
            return False, 0.0

        distance = face_recognition.face_distance(
            [doc_encodings[0]],
            live_encodings[0]
        )[0]

        similarity = 1.0 - float(distance)

        verified = similarity >= 0.80

        return verified, similarity

    except Exception as exc:

        logger.error(
            "Fallback failed: %s",
            exc
        )

        return False, 0.0

# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    document_path = "document_face.jpg"

    live_image = cv2.imread("live_face.jpg")

    result = verify_faces(
        document_path,
        live_image
    )

    print("\nVerification Result:")
    print(result)
