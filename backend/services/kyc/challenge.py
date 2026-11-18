"""
Active liveness: a server-issued, random, single-use head-turn challenge.

The browser captures one frame for each step. The server measures normalized yaw from MTCNN
landmarks and checks a minimum directional change of 0.12 for each requested turn. Nothing the
browser claims is trusted.

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
MAX_START_YAW = 0.20


def new_challenge() -> dict:
    """Issue a baseline and a randomized left/right turn sequence."""
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
    """Signed normalized yaw ratio, or None when no usable face is found."""
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
    """Pass only when both requested directional yaw changes meet the minimum."""
    yaws = list(yaws)
    if len(yaws) != len(steps) or not steps or steps[0] != "center":
        return ChallengeResult("FAIL", ["the head-turn frames do not match the challenge"], yaws)
    if any(yaw is None for yaw in yaws):
        return ChallengeResult("UNCERTAIN", ["no face found in one of the head-turn frames — retake"], yaws)
    if not frames_distinct:
        return ChallengeResult("FAIL", ["head-turn frames are identical — static image"], yaws)

    base = yaws[0]
    if abs(base) > MAX_START_YAW:
        return ChallengeResult("UNCERTAIN", ["face was not looking straight at the start — retake"], yaws)

    need = liveness_min_turn_ratio()
    reasons = []
    for step, yaw in zip(steps[1:], yaws[1:]):
        delta = yaw - base
        # The webcam preview is mirrored for the user, while submitted pixels are not.
        # On this pipeline the user's left turn therefore produces a negative yaw delta.
        ok = delta <= -need if step == "left" else delta >= need
        if not ok:
            reasons.append(f"head did not turn {step} as asked (change {delta:+.2f}, needed {need:.2f})")
    return ChallengeResult("FAIL", reasons, yaws) if reasons else ChallengeResult("PASS", [], yaws)


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
