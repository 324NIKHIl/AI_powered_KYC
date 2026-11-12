"""
OpenCV-based image preprocessing utilities.
All functions return numpy arrays (BGR) or save files and return paths.
"""

from __future__ import annotations

import base64
import io
import os
import uuid
import logging

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


def _ensure_min_face_size(face: np.ndarray, min_size: int = 224) -> np.ndarray:
    h, w = face.shape[:2]
    shortest = min(h, w)
    if shortest >= min_size:
        return face
    scale = min_size / max(1, shortest)
    return cv2.resize(face, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)


# ── Encode / Decode helpers ───────────────────────────────────────────────────

def base64_to_numpy(b64_string: str) -> np.ndarray:
    """Convert a base64-encoded image string to a BGR numpy array."""
    # Strip data-URL prefix if present
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    raw = base64.b64decode(b64_string)
    pil = Image.open(io.BytesIO(raw)).convert("RGB")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def numpy_to_base64(img: np.ndarray) -> str:
    """Convert a BGR numpy array to a base64-encoded PNG string."""
    _, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf).decode("utf-8")


def pil_to_numpy(pil_img: Image.Image) -> np.ndarray:
    rgb = pil_img.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


# ── Preprocessing pipeline ────────────────────────────────────────────────────

def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """
    Full preprocessing pipeline to improve OCR accuracy:
    grayscale → denoise → adaptive threshold → sharpen
    """
    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # 3. Adaptive threshold (handles uneven lighting)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11,
        C=2,
    )

    # 4. Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(thresh, -1, kernel)

    # Return as 3-channel so EasyOCR is happy
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    """CLAHE contrast enhancement — useful for poorly lit ID cards."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def deskew(img: np.ndarray) -> np.ndarray:
    """Correct minor rotation in scanned documents."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=80, maxLineGap=10)
    if lines is None:
        return img
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < 45:
            angles.append(angle)
    if not angles:
        return img
    median_angle = np.median(angles)
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), median_angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


# ── Face detection & alignment ────────────────────────────────────────────────

# Canonical landmark positions of a 112×112 ArcFace input (InsightFace template):
# left eye, right eye, nose tip, left mouth corner, right mouth corner.
# Recognition models are trained on faces warped onto exactly these points, so
# embeddings of unaligned / loosely cropped faces are unreliable.
ARCFACE_LANDMARKS = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)
_LANDMARK_KEYS = ("left_eye", "right_eye", "nose", "mouth_left", "mouth_right")

MIN_FACE_CONFIDENCE = 0.90

_mtcnn_detector = None


def _get_mtcnn():
    """MTCNN builds several TF graphs on construction — create it once."""
    global _mtcnn_detector
    if _mtcnn_detector is None:
        from mtcnn import MTCNN
        _mtcnn_detector = MTCNN()
    return _mtcnn_detector


def _scale_detection(det: dict, factor: float) -> dict:
    x, y, w, h = det["box"]
    return {
        **det,
        "box": [int(x * factor), int(y * factor), int(w * factor), int(h * factor)],
        "keypoints": {k: (p[0] * factor, p[1] * factor) for k, p in det["keypoints"].items()},
    }


def detect_faces(img: np.ndarray, min_confidence: float = MIN_FACE_CONFIDENCE) -> list[dict]:
    """
    Run MTCNN and return confident detections, largest face first.
    Each detection has "box" (x, y, w, h), "confidence" and "keypoints".
    Small images (e.g. a low-res scan where the ID photo is tiny) are retried
    at 2× since MTCNN misses faces below ~20 px.
    """
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    detector = _get_mtcnn()
    faces = [d for d in detector.detect_faces(rgb) if d["confidence"] >= min_confidence]

    if not faces and max(img.shape[:2]) < 1000:
        big = cv2.resize(rgb, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        faces = [
            _scale_detection(d, 0.5)
            for d in detector.detect_faces(big)
            if d["confidence"] >= min_confidence
        ]

    return sorted(faces, key=lambda d: d["box"][2] * d["box"][3], reverse=True)


def _similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform (Umeyama) mapping src points onto dst, as a 2×3 matrix."""
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_c, dst_c = src - src_mean, dst - dst_mean
    u, s, vt = np.linalg.svd(dst_c.T @ src_c / len(src))
    d = np.ones(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        d[-1] = -1
    rotation = u @ np.diag(d) @ vt
    scale = (s * d).sum() / src_c.var(axis=0).sum()
    translation = dst_mean - scale * rotation @ src_mean
    return np.hstack([scale * rotation, translation[:, None]])


def align_face(img: np.ndarray, keypoints: dict, size: int = 112) -> np.ndarray:
    """Warp a face onto the ArcFace landmark template, returning a size×size BGR crop."""
    src = np.array([keypoints[k] for k in _LANDMARK_KEYS], dtype=np.float64)
    dst = ARCFACE_LANDMARKS.astype(np.float64) * (size / 112.0)
    matrix = _similarity_transform(src, dst)
    return cv2.warpAffine(img, matrix, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def crop_face(img: np.ndarray, box, pad_ratio: float = 0.45) -> np.ndarray:
    """Padded crop around a detection box — for display / audit, not for embeddings."""
    x, y, w, h = box
    pad = int(max(w, h) * pad_ratio)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img.shape[1], x + w + pad)
    y2 = min(img.shape[0], y + h + pad)
    return _ensure_min_face_size(img[y1:y2, x1:x2])


# ── Face extraction from document ─────────────────────────────────────────────

def extract_face_opencv(img: np.ndarray) -> np.ndarray | None:
    """
    Fallback Haar-cascade face detection when MTCNN is unavailable.
    Returns the first detected face crop, padded 20 %.
    """
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(faces) == 0:
        return None
    box = max(faces, key=lambda r: r[2] * r[3])
    return crop_face(img, box, pad_ratio=0.35)


def extract_face_mtcnn(img: np.ndarray) -> np.ndarray | None:
    """
    MTCNN-based face detection — more accurate than Haar cascades.
    Returns a padded crop of the largest confident face (the main ID photo,
    not a ghost image / emblem). Falls back to opencv on failure.
    """
    try:
        faces = detect_faces(img)
        if not faces:
            return extract_face_opencv(img)
        return crop_face(img, faces[0]["box"])
    except Exception as exc:
        logger.warning("MTCNN failed (%s), falling back to OpenCV", exc)
        return extract_face_opencv(img)


# ── File I/O helpers ──────────────────────────────────────────────────────────

def save_image(img: np.ndarray, directory: str, prefix: str = "img") -> str:
    """Save numpy array as JPEG and return the relative path."""
    os.makedirs(directory, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
    path = os.path.join(directory, filename)
    cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return path


async def save_upload_bytes(data: bytes, directory: str, original_filename: str) -> tuple[str, np.ndarray]:
    """
    Persist raw upload bytes to disk and return (path, numpy_array).
    Handles JPEG, PNG, and PDF (first page via pdf2image).
    """
    ext = os.path.splitext(original_filename)[1].lower()
    file_id = uuid.uuid4().hex[:12]
    os.makedirs(directory, exist_ok=True)

    if ext == ".pdf":
        # Save PDF then convert first page to image
        pdf_path = os.path.join(directory, f"doc_{file_id}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(data)
        try:
            from pdf2image import convert_from_bytes
            pages = convert_from_bytes(data, first_page=1, last_page=1)
            img = pil_to_numpy(pages[0])
        except Exception as exc:
            raise ValueError(f"PDF conversion failed: {exc}") from exc
        save_path = os.path.join(directory, f"doc_{file_id}.jpg")
        cv2.imwrite(save_path, img)
    else:
        save_path = os.path.join(directory, f"doc_{file_id}{ext}")
        with open(save_path, "wb") as f:
            f.write(data)
        # Phone photos are often stored sideways with an EXIF "rotate" tag; apply it, otherwise the OCR
        # and face detector see the document turned 90° and read nothing.
        pil = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    return save_path, img
