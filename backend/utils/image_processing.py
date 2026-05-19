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
from PIL import Image

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
    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
    pad = int(max(w, h) * 0.35)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img.shape[1], x + w + pad)
    y2 = min(img.shape[0], y + h + pad)
    return _ensure_min_face_size(img[y1:y2, x1:x2])


def extract_face_mtcnn(img: np.ndarray) -> np.ndarray | None:
    """
    MTCNN-based face detection — more accurate than Haar cascades.
    Falls back to opencv on failure.
    """
    try:
        from mtcnn import MTCNN
        detector = MTCNN()
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = detector.detect_faces(rgb)
        if not results:
            return extract_face_opencv(img)
        # Pick highest-confidence detection
        best = max(results, key=lambda r: r["confidence"])
        if best["confidence"] < 0.75:
            return extract_face_opencv(img)
        x, y, w, h = best["box"]
        pad = int(max(w, h) * 0.45)
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img.shape[1], x + w + pad)
        y2 = min(img.shape[0], y + h + pad)
        return _ensure_min_face_size(img[y1:y2, x1:x2])
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
        pil = Image.open(io.BytesIO(data)).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    return save_path, img
