"""
Active liveness: a server-issued, random, single-use head-turn challenge.

The server picks the sequence (straight → turn one way → turn the other way, order random), the
browser captures one frame per step, and the *server* measures the head yaw in every frame from the
MTCNN landmarks: yaw = (nose_x − eye_midpoint_x) / eye_distance. A real head turning moves the nose
sideways relative to the eyes; a photo/screen held up to the camera keeps that ratio almost
constant, so it cannot follow a random prompt. Nothing the browser claims is trusted.

Limits: a pre-recorded video of the person (or a virtual camera) can still follow prompts; this is
not certified PAD. Layer a vendor/ML PAD model behind `assess_liveness` for high-assurance use.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from services.kyc.config import liveness_challenge_ttl_s, liveness_min_turn_ratio

logger = logging.getLogger(__name__)

PROMPTS = {
    "center": "Look straight at the camera",
    "left":   "Slowly turn your head to the LEFT",
    "right":  "Slowly turn your head to the RIGHT",
}
MAX_START_YAW = 0.20     # the first (straight) frame must be roughly frontal


def new_challenge() -> dict:
    """A fresh challenge document (stored in the session; the browser only gets id + steps)."""
    turns = ["left", "right"]
    if secrets.randbelow(2):
        turns.reverse()
    return {
        "id": secrets.token_urlsafe(16),
        "steps": ["center", *turns],
        "expires_at": time.time() + liveness_challenge_ttl_s(),
        "used": False,
    }


def public_view(ch: dict) -> dict:
    return {
        "challenge_id": ch["id"],
        "steps": [{"id": s, "prompt": PROMPTS[s]} for s in ch["steps"]],
        "expires_in": liveness_challenge_ttl_s(),
    }


def check_challenge_usable(ch: Optional[dict], challenge_id: Optional[str]) -> Optional[str]:
    """None when the challenge may be used, else the reason it can't."""
    if not ch or not challenge_id:
        return "no head-turn challenge was issued for this session"
    if not secrets.compare_digest(str(ch.get("id", "")), str(challenge_id)):
        return "the head-turn challenge does not match the one issued"
    if ch.get("used"):
        return "the head-turn challenge was already used"
    if time.time() > float(ch.get("expires_at", 0)):
        return "the head-turn challenge expired"
    return None


@dataclass
class ChallengeResult:
    status: str                       # PASS | FAIL | UNCERTAIN
    reasons: list[str] = field(default_factory=list)
    yaws: list[Optional[float]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict:
        return {"status": self.status, "reasons": self.reasons,
                "yaws": [None if y is None else round(y, 3) for y in self.yaws]}


def measure_yaw(frame: np.ndarray, detect: Optional[Callable] = None) -> Optional[float]:
    """Signed yaw ratio of the largest face (image coordinates), or None if no face was found."""
    if detect is None:
        from utils.image_processing import detect_faces
        detect = detect_faces
    faces = detect(frame)
    if not faces:
        return None
    kp = faces[0]["keypoints"]
    le, re_, nose = (np.array(kp[k], dtype=np.float64) for k in ("left_eye", "right_eye", "nose"))
    eye_dist = float(np.linalg.norm(re_ - le))
    if eye_dist < 8:
        return None
    return float((nose[0] - (le[0] + re_[0]) / 2) / eye_dist)


def evaluate(steps: Sequence[str], yaws: Sequence[Optional[float]], frames_distinct: bool = True) -> ChallengeResult:
    """Decide the challenge from the measured yaw of each step's frame."""
    yaws = list(yaws)
    if len(yaws) != len(steps) or steps[0] != "center":
        return ChallengeResult("FAIL", ["the head-turn frames do not match the challenge"], yaws)
    if any(y is None for y in yaws):
        return ChallengeResult("UNCERTAIN", ["no face found in one of the head-turn frames — retake"], yaws)
    if not frames_distinct:
        return ChallengeResult("FAIL", ["head-turn frames are identical — static image"], yaws)

    base = yaws[0]
    if abs(base) > MAX_START_YAW:
        return ChallengeResult("UNCERTAIN", ["face was not looking straight at the start — retake"], yaws)

    need = liveness_min_turn_ratio()
    reasons: list[str] = []
    for step, y in zip(steps[1:], yaws[1:]):
        delta = y - base
        # "left" = the nose moves towards the left of the (mirrored, selfie-style) image
        ok = delta <= -need if step == "left" else delta >= need
        if not ok:
            reasons.append(f"head did not turn {step} as asked (change {delta:+.2f}, needed {need:.2f})")
    if reasons:
        return ChallengeResult("FAIL", reasons, yaws)
    return ChallengeResult("PASS", [], yaws)


def verify_challenge(
    steps: Sequence[str],
    frames: Sequence[np.ndarray],
    raw_frames: Sequence[bytes | str] = (),
    detect: Optional[Callable] = None,
) -> ChallengeResult:
    distinct = len(set(raw_frames)) == len(raw_frames) if raw_frames else True
    yaws = [measure_yaw(f, detect) for f in frames]
    result = evaluate(steps, yaws, distinct)
    logger.info("head-turn challenge %s yaws=%s", result.status, result.to_dict()["yaws"])
    return result
