"""
Face-alteration / synthetic-face heuristics.

Looks for the statistical seams that face swaps, blended edits and generated faces tend
to leave: texture/noise statistics of the face region that disagree with the rest of the
same frame, a colour discontinuity between face and neck, and anomalous high-frequency
spectrum energy. Heuristic and uncalibrated — a high score means "inspect this", a low
score is NOT proof the face is genuine. Plug a trained deepfake classifier in behind
`assess_face_alteration` for production (same return type).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import cv2
import numpy as np

from services.kyc.config import deepfake_high_threshold, deepfake_review_threshold

logger = logging.getLogger(__name__)


@dataclass
class DeepfakeResult:
    risk: float
    level: str                                   # LOW | REVIEW | HIGH
    signals: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    method: str = "statistical-heuristic"

    def to_dict(self) -> dict:
        return {"risk": round(self.risk, 3), "level": self.level,
                "signals": {k: round(v, 3) for k, v in self.signals.items()},
                "reasons": self.reasons, "method": self.method}


def _noise_level(gray: np.ndarray) -> float:
    resid = gray.astype(np.float32) - cv2.GaussianBlur(gray, (0, 0), 1.2).astype(np.float32)
    return float(np.median(np.abs(resid)) + 1e-3)


def _ela_level(img: np.ndarray) -> float:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return 0.0
    return float(cv2.absdiff(img, cv2.imdecode(buf, cv2.IMREAD_COLOR)).mean()) + 1e-3


def _hf_ratio(gray: np.ndarray) -> float:
    g = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32)
    mag = np.abs(np.fft.fftshift(np.fft.fft2((g - g.mean()) * np.outer(np.hanning(128), np.hanning(128)))))
    yy, xx = np.indices(mag.shape)
    r = np.hypot(yy - 64, xx - 64)
    hi, mid = mag[(r > 40) & (r <= 62)].mean(), mag[(r > 12) & (r <= 30)].mean()
    return float(hi / (mid + 1e-6))


def assess_face_alteration(
    frame: np.ndarray,
    face_box: Optional[Sequence[int]],
) -> DeepfakeResult:
    signals: dict[str, float] = {}
    reasons: list[str] = []
    if face_box is None:
        return DeepfakeResult(0.0, "LOW", {}, ["no face region available for analysis"])

    x, y, w, h = [int(v) for v in face_box]
    H, W = frame.shape[:2]
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    if w < 48 or h < 48:
        return DeepfakeResult(0.0, "LOW", {}, ["face too small for alteration analysis"])

    # Inner face (avoid hair/background at the box edges)
    ix, iy, iw, ih = x + w // 6, y + h // 6, w * 2 // 3, h * 2 // 3
    face = frame[iy:iy + ih, ix:ix + iw]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    fgray = gray[iy:iy + ih, ix:ix + iw]

    # Background reference: a band around the face box (same camera, same compression)
    mask = np.ones(gray.shape, np.uint8)
    pad = max(w, h) // 3
    mask[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)] = 0

    # 1) face vs. rest-of-frame noise & sharpness mismatch (pasted/smoothed faces)
    if int(mask.sum()) > 4000:
        # compute on valid 32x32 patches outside the face box
        patches = []
        for py in range(0, H - 32, 32):
            for px in range(0, W - 32, 32):
                if mask[py:py + 32, px:px + 32].all():
                    patches.append(_noise_level(gray[py:py + 32, px:px + 32]))
        if len(patches) >= 6:
            bg_n = float(np.median(patches))
            face_n = _noise_level(fgray)
            ratio = face_n / bg_n
            # smooth face on a noisy frame (ratio<<1) or inverse
            signals["noise_mismatch"] = float(np.clip(abs(np.log2(ratio)) - 1.0, 0.0, 2.0) / 2.0)
            if signals["noise_mismatch"] > 0.5:
                reasons.append("face region has a different noise/sharpness level from the rest of the image")

    # 2) face vs. neck colour discontinuity (blended swaps)
    ny0, ny1 = min(H, y + h), min(H, y + h + h // 3)
    if ny1 - ny0 >= 10:
        neck = frame[ny0:ny1, x + w // 4: x + 3 * w // 4]
        if neck.size and face.size:
            lab_f = cv2.cvtColor(face, cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(axis=0)
            lab_n = cv2.cvtColor(neck, cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(axis=0)
            delta = float(np.hypot(lab_f[1] - lab_n[1], lab_f[2] - lab_n[2]))
            signals["skin_tone_break"] = float(np.clip((delta - 14.0) / 18.0, 0.0, 1.0))
            if signals["skin_tone_break"] > 0.5:
                reasons.append("skin tone changes abruptly between face and neck")

    # 3) face-region re-compression error vs the frame (spliced content)
    full_ela, face_ela = _ela_level(frame), _ela_level(face)
    signals["recompression_mismatch"] = float(np.clip(abs(np.log2(face_ela / full_ela)) - 1.2, 0.0, 2.0) / 2.0)
    if signals["recompression_mismatch"] > 0.5:
        reasons.append("face region was compressed differently from the rest of the image")

    # 4) high-frequency spectrum anomaly (generator up-sampling)
    hf = _hf_ratio(fgray)
    signals["spectral_anomaly"] = float(np.clip((hf - 0.55) / 0.5, 0.0, 1.0))
    if signals["spectral_anomaly"] > 0.5:
        reasons.append("unusual high-frequency spectrum, typical of synthetic imagery")

    weights = {"noise_mismatch": 0.6, "skin_tone_break": 0.6, "recompression_mismatch": 0.5, "spectral_anomaly": 0.5}
    risk = 1.0 - float(np.prod([1.0 - signals[k] * weights[k] for k in signals])) if signals else 0.0
    high, review = deepfake_high_threshold(), deepfake_review_threshold()
    level = "HIGH" if risk >= high else "REVIEW" if risk >= review else "LOW"
    logger.info("face-alteration risk=%.3f level=%s", risk, level)
    return DeepfakeResult(risk, level, signals, reasons)
