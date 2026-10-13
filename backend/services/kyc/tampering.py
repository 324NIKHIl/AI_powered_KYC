"""
Fraud / tampering analysis for document images.

These are *heuristics*: they can raise suspicion (and a strong signal triggers
SUSPICIOUS) but a clean result is never evidence of authenticity. Signals:
  • editing-software metadata (EXIF Software tag)
  • Error-Level Analysis (ELA): re-compression error that is locally very different
    from the rest of the image → pasted/edited region   (JPEG sources only)
  • local noise-residual inconsistency: a patch with a different sensor-noise level
    from its surroundings → composited content
"""

from __future__ import annotations

import io
import logging
import warnings
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

EDITOR_MARKERS = (
    "photoshop", "gimp", "canva", "pixlr", "snapseed", "lightroom", "paint.net", "picsart",
    "affinity", "illustrator", "coreldraw", "fotor", "photopea", "faceapp", "facetune",
)
BLOCK = 24
Z_THRESHOLD = 7.0


@dataclass
class TamperReport:
    score: float = 0.0
    indicators: list[str] = field(default_factory=list)
    applicable: dict[str, bool] = field(default_factory=dict)


def _metadata_signal(raw: bytes) -> tuple[float, str | None]:
    try:
        with Image.open(io.BytesIO(raw)) as im:
            software = str(im.getexif().get(305, "") or "")
            info = " ".join(str(v) for v in im.info.values() if isinstance(v, (str, bytes)))[:2000]
    except Exception:
        return 0.0, None
    blob = f"{software} {info}".lower()
    for marker in EDITOR_MARKERS:
        if marker in blob:
            return 0.45, f"image metadata names editing software ({marker})"
    return 0.0, None


def _outlier_block_score(values: np.ndarray, min_cluster: int = 3) -> float:
    """Score how strongly a *cluster* of blocks deviates from the median (robust z-score)."""
    if values.size < 30:
        return 0.0
    median = np.median(values)
    mad = np.median(np.abs(values - median)) * 1.4826 + 1e-6
    z = np.abs(values - median) / mad
    mask = (z > Z_THRESHOLD).astype(np.uint8)
    if mask.sum() < min_cluster:
        return 0.0
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if count > 1 else 0
    if largest < min_cluster:
        return 0.0
    fraction = largest / values.size
    return float(min(1.0, 0.35 + fraction * 8))


def _block_map(arr: np.ndarray) -> np.ndarray:
    h, w = arr.shape[:2]
    h2, w2 = h - h % BLOCK, w - w % BLOCK
    arr = arr[:h2, :w2]
    return arr.reshape(h2 // BLOCK, BLOCK, w2 // BLOCK, BLOCK).mean(axis=(1, 3))


def _ela_signal(img: np.ndarray) -> float:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return 0.0
    recompressed = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(img, recompressed).astype(np.float32).mean(axis=2)
    return _outlier_block_score(_block_map(diff).ravel())


def _noise_signal(gray: np.ndarray) -> float:
    residual = np.abs(gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32))
    # Flat regions only: edges/text dominate residual and would mask noise differences
    edges = cv2.dilate(cv2.Canny(gray, 60, 140), np.ones((5, 5), np.uint8)) > 0
    residual[edges] = np.nan
    h, w = residual.shape
    h2, w2 = h - h % BLOCK, w - w % BLOCK
    blocks = residual[:h2, :w2].reshape(h2 // BLOCK, BLOCK, w2 // BLOCK, BLOCK)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        means = np.nanmean(blocks, axis=(1, 3))
    valid = np.isfinite(means)
    if valid.sum() < 30:
        return 0.0
    filled = np.where(valid, means, np.nanmedian(means))
    return _outlier_block_score(filled.ravel(), min_cluster=4) * 0.8


def analyse_tampering(img: np.ndarray, raw_bytes: bytes | None = None, source_is_jpeg: bool = True) -> TamperReport:
    report = TamperReport()
    scores: list[float] = []

    if raw_bytes:
        s, why = _metadata_signal(raw_bytes)
        if s and why:
            scores.append(s)
            report.indicators.append(why)

    h, w = img.shape[:2]
    scale = 1400.0 / max(h, w)
    work = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img

    report.applicable["ela"] = source_is_jpeg
    if source_is_jpeg:
        try:
            s = _ela_signal(work)
            if s > 0:
                scores.append(s)
                report.indicators.append("re-compression error is inconsistent across the image (possible edited region)")
        except Exception:
            logger.exception("ELA failed")

    try:
        s = _noise_signal(cv2.cvtColor(work, cv2.COLOR_BGR2GRAY))
        report.applicable["noise"] = True
        if s > 0:
            scores.append(s)
            report.indicators.append("a region has a different noise pattern from the rest of the image")
    except Exception:
        logger.exception("noise analysis failed")

    # Independent signals combine: P(at least one is real) — corroboration raises the score
    combined = 1.0 - float(np.prod([1.0 - s for s in scores])) if scores else 0.0
    report.score = round(min(1.0, combined), 3)
    return report
