"""
Final identity decision: combines the document verification with face match, liveness and
face-alteration analysis. The browser never decides anything — this runs on the backend.

Precedence (most severe first):
  SUSPICIOUS > REJECTED > (capture problem → MANUAL) > VERIFICATION_UNAVAILABLE > MANUAL > VERIFIED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models.verification import KycStatus, VerificationStatus
from services.kyc.config import face_match_threshold, face_no_match_threshold
from services.kyc.deepfake import DeepfakeResult
from services.kyc.liveness import LivenessResult, LivenessStatus


class FaceMatch:
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    UNCERTAIN = "UNCERTAIN"


def classify_similarity(similarity: float) -> str:
    """MATCH ≥ match threshold; NO_MATCH < no-match threshold; UNCERTAIN in between (both configurable)."""
    if similarity >= face_match_threshold():
        return FaceMatch.MATCH
    if similarity < face_no_match_threshold():
        return FaceMatch.NO_MATCH
    return FaceMatch.UNCERTAIN


@dataclass
class IdentityDecision:
    status: KycStatus
    reasons: list[str] = field(default_factory=list)
    risk_score: float = 0.0

    @property
    def legacy_decision(self) -> VerificationStatus:
        """Map onto the pre-existing APPROVED / REJECTED / PENDING values used by the admin views."""
        if self.status == KycStatus.VERIFIED:
            return VerificationStatus.APPROVED
        if self.status in (KycStatus.REJECTED, KycStatus.SUSPICIOUS):
            return VerificationStatus.REJECTED
        return VerificationStatus.PENDING


def decide_identity(
    *,
    document_status: Optional[str],
    document_risk: float,
    face_status: Optional[str],            # MATCH | NO_MATCH | UNCERTAIN | None (could not compare)
    capture_issue: Optional[str],          # human-readable reason the selfie couldn't be used, if any
    liveness: Optional[LivenessResult],
    deepfake: Optional[DeepfakeResult],
    extra_tamper_flags: list[str],
    similarity: float = 0.0,
) -> IdentityDecision:
    from services.kyc.config import deepfake_high_threshold, deepfake_review_threshold

    suspicious: list[str] = []
    rejected: list[str] = []
    unavailable: list[str] = []
    manual: list[str] = []

    if document_status == "SUSPICIOUS":
        suspicious.append("Document shows signs of manipulation or inconsistent data")
    suspicious.extend(extra_tamper_flags)
    if liveness and liveness.status == LivenessStatus.FAIL:
        suspicious.append("Live capture looks like a presentation attack: " + "; ".join(liveness.reasons or ["screen/print artefacts"]))
    if deepfake and deepfake.risk >= deepfake_high_threshold():
        suspicious.append("Live capture shows signs of face manipulation: " + "; ".join(deepfake.reasons or ["synthetic-face indicators"]))

    if document_status == "INVALID":
        rejected.append("Document failed validation")
    if face_status == FaceMatch.NO_MATCH:
        rejected.append("Live face does not match the document photo")

    if document_status == "VERIFICATION_UNAVAILABLE":
        unavailable.append("Document authenticity could not be verified: the authoritative source/key was unavailable")
    if document_status in (None, "MANUAL_REVIEW_REQUIRED"):
        manual.append("Document authenticity could not be determined automatically")
    if face_status == FaceMatch.UNCERTAIN:
        manual.append(f"Face similarity ({similarity:.2f}) is inconclusive")
    if liveness and liveness.status == LivenessStatus.UNCERTAIN:
        manual.append("Liveness could not be confirmed" + (": " + "; ".join(liveness.reasons) if liveness.reasons else ""))
    if deepfake and deepfake_between(deepfake, deepfake_review_threshold(), deepfake_high_threshold()):
        manual.append("Possible face alteration — review the capture")
    if capture_issue:
        manual.append(capture_issue)

    # Combined risk: independent evidence of fraud compounds
    face_risk = {FaceMatch.MATCH: 0.0, FaceMatch.UNCERTAIN: 0.5, FaceMatch.NO_MATCH: 0.9}.get(face_status or "", 0.4)
    parts = [document_risk, face_risk, 0.8 * (liveness.attack_score if liveness else 0.3),
             0.8 * (deepfake.risk if deepfake else 0.0)]
    risk = 1.0
    for p in parts:
        risk *= 1.0 - max(0.0, min(1.0, p))
    risk = round(1.0 - risk, 3)

    if suspicious:
        return IdentityDecision(KycStatus.SUSPICIOUS, suspicious + rejected, max(risk, 0.8))
    if rejected:
        return IdentityDecision(KycStatus.REJECTED, rejected, max(risk, 0.7))
    if capture_issue:
        return IdentityDecision(KycStatus.MANUAL_REVIEW_REQUIRED, manual + unavailable, risk)
    if unavailable:
        return IdentityDecision(KycStatus.VERIFICATION_UNAVAILABLE, unavailable + manual, risk)
    if manual:
        return IdentityDecision(KycStatus.MANUAL_REVIEW_REQUIRED, manual, risk)
    return IdentityDecision(KycStatus.VERIFIED, [], risk)


def deepfake_between(d: DeepfakeResult, low: float, high: float) -> bool:
    return low <= d.risk < high
