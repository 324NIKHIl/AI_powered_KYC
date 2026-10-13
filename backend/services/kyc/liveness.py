"""
Passive presentation-attack (PAD) heuristics for the live capture.

Detects the *artefacts* of: a phone/monitor screen (moiré, glare), a printed photo or
a static image (no temporal variation, flat texture), and a replayed still.
These are classical signal-processing heuristics with configurable thresholds — NOT a trained
anti-spoofing network. They catch crude attacks and raise review flags; a determined attacker
(high-resolution screen, 3D mask, injected virtual camera) can defeat them. For production,
add a certified PAD model/vendor behind `assess_liveness` (same return type).

Trust model: the browser's liveness-challenge flag can only make the result *stricter*
(challenge not completed → UNCERTAIN). A client claim of success is never accepted as proof.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

import cv2
import numpy as np

from services.kyc.config import liveness_fail_threshold, liveness_uncertain_threshold

logger = logging.getLogger(__name__)


class LivenessStatus(str, Enum):
    PASS      = "PASS"
    FAIL      = "FAIL"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class LivenessResult:
    status: LivenessStatus
    attack_score: float                       # 0 = looks live, 1 = looks like an attack
    signals: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    frames_analysed: int = 1
    method: str = "passive-heuristic"

    def to_dict(self) -> dict:
        return {"status": self.status.value, "attack_score": round(self.attack_score, 3),
                "signals": {k: round(v, 3) for k, v in self.signals.items()},
                "reasons": self.reasons, "frames_analysed": self.frames_analysed, "method": self.method}


def _crop(img: np.ndarray, box: Optional[Sequence[int]], pad: float = 0.15) -> np.ndarray:
    if box is None:
        return img
    x, y, w, h = [int(v) for v in box]
    H, W = img.shape[:2]
    px, py = int(w * pad), int(h * pad)
    x0, y0, x1, y1 = max(0, x - px), max(0, y - py), min(W, x + w + px), min(H, y + h + py)
    crop = img[y0:y1, x0:x1]
    return crop if crop.size and min(crop.shape[:2]) >= 32 else img


def moire_score(gray: np.ndarray) -> float:
    """Screens re-imaged by a camera leave narrow, strong peaks in the mid/high-frequency spectrum."""
    g = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32)
    g -= g.mean()
    window = np.outer(np.hanning(256), np.hanning(256)).astype(np.float32)
    mag = np.abs(np.fft.fftshift(np.fft.fft2(g * window)))
    yy, xx = np.indices(mag.shape)
    r = np.hypot(yy - 128, xx - 128)
    band = (r > 24) & (r < 120)
    values = mag[band]
    if values.size == 0:
        return 0.0
    # Peak prominence against the local (radially-matched) average, not the global median
    bins = r[band].astype(int)
    radial_mean = np.bincount(bins, weights=values) / np.maximum(np.bincount(bins), 1)
    prominence = values / (radial_mean[bins] + 1e-6)
    top = np.sort(prominence)[-5:].mean()
    return float(np.clip((top - 9.0) / 18.0, 0.0, 1.0))


def glare_score(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    frac = float((gray >= 252).mean())
    return float(np.clip((frac - 0.01) / 0.08, 0.0, 1.0))


def flatness_score(face: np.ndarray) -> float:
    """Reprinted/re-photographed faces lose fine texture and chroma range."""
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)
    texture = float(cv2.Laplacian(small, cv2.CV_64F).var())
    sat = float(cv2.cvtColor(face, cv2.COLOR_BGR2HSV)[..., 1].std())
    tex_s = float(np.clip((25.0 - texture) / 25.0, 0.0, 1.0))
    sat_s = float(np.clip((12.0 - sat) / 12.0, 0.0, 1.0))
    return 0.6 * tex_s + 0.4 * sat_s


def monochrome_score(face: np.ndarray) -> float:
    """A live colour webcam never produces an (almost) colourless face; B/W prints and screens do."""
    mean_sat = float(cv2.cvtColor(face, cv2.COLOR_BGR2HSV)[..., 1].mean())
    return float(np.clip((18.0 - mean_sat) / 14.0, 0.0, 1.0))


def temporal_score(frames: Sequence[np.ndarray], box: Optional[Sequence[int]]) -> Optional[float]:
    """Identical frames ⇒ a still image / frozen replay; a live face always varies slightly."""
    if len(frames) < 2:
        return None
    grays = []
    for f in frames:
        c = _crop(f, box, 0.3)
        grays.append(cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), (96, 96)).astype(np.float32))
    diffs = [float(np.abs(a - b).mean()) for a, b in zip(grays, grays[1:])]
    mean_diff = float(np.mean(diffs))
    return float(np.clip((1.2 - mean_diff) / 1.2, 0.0, 1.0))


def assess_liveness(
    frame: np.ndarray,
    face_box: Optional[Sequence[int]] = None,
    extra_frames: Sequence[np.ndarray] = (),
    client_challenge_passed: Optional[bool] = None,
) -> LivenessResult:
    face = _crop(frame, face_box)
    signals = {
        "screen_moire": moire_score(cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)),
        "glare": glare_score(face),
        "flat_texture": flatness_score(face),
        "monochrome": monochrome_score(face),
    }
    # Whole-frame moiré catches a screen even when the face crop is small
    signals["screen_moire_frame"] = moire_score(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    temporal = temporal_score([frame, *extra_frames], face_box)
    if temporal is not None:
        signals["static_frames"] = temporal

    weights = {"screen_moire": 0.9, "screen_moire_frame": 0.6, "glare": 0.35, "flat_texture": 0.45, "monochrome": 0.7, "static_frames": 0.9}
    attack = 1.0 - float(np.prod([1.0 - signals[k] * weights[k] for k in signals]))

    reasons: list[str] = []
    if signals["screen_moire"] > 0.4 or signals["screen_moire_frame"] > 0.5:
        reasons.append("periodic screen/moiré patterns detected")
    if signals["glare"] > 0.5:
        reasons.append("strong specular glare (screen or glossy print)")
    if signals["monochrome"] > 0.5:
        reasons.append("face is colourless — black-and-white print or monitor")
    if signals["flat_texture"] > 0.35:
        reasons.append("face lacks natural skin texture and colour variation")
    if signals.get("static_frames", 0) > 0.7:
        reasons.append("captured frames are identical — static image or frozen replay")

    fail_t, unc_t = liveness_fail_threshold(), liveness_uncertain_threshold()
    if attack >= fail_t:
        status = LivenessStatus.FAIL
    elif attack >= unc_t:
        status = LivenessStatus.UNCERTAIN
    else:
        status = LivenessStatus.PASS

    # The client may only tighten the result, never loosen it
    if client_challenge_passed is False and status == LivenessStatus.PASS:
        status = LivenessStatus.UNCERTAIN
        reasons.append("the on-screen liveness challenge was not completed")
    if temporal is None and status == LivenessStatus.PASS:
        reasons.append("single frame only — temporal checks were not possible")

    logger.info("liveness status=%s attack=%.3f frames=%d", status.value, attack, 1 + len(extra_frames))
    return LivenessResult(status, attack, signals, reasons, frames_analysed=1 + len(extra_frames))
