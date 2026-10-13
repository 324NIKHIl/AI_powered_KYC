"""
Decision logic. The rule that matters:

    "I read this document"  !=  "I have evidence this document is authentic"

VALID is reachable only through authoritative evidence — a verified issuer
signature, or a genuine (non-mock) match from an external authoritative source —
plus every document-specific required check passing. OCR success, regex/format
validity and MRZ check digits are *necessary* but never *sufficient*.
"""

from __future__ import annotations

from services.kyc.config import tamper_suspicious_threshold
from services.kyc.result import (
    CheckOutcome,
    DocStatus,
    DocumentVerification,
    EvidenceLevel,
)

# Checks that must PASS (not merely be absent) before a document can be VALID
REQUIRED_PASS: dict[str, tuple[str, ...]] = {
    "AADHAAR": ("qr_consistent",),
    "PAN": ("pan_format",),
    "PASSPORT": ("mrz_checksums",),
    "DRIVING_LICENCE": ("dl_format",),
    "CITIZENSHIP": ("cz_number",),
    "EDUCATION": ("edu_roll",),
}


def evidence_level(v: DocumentVerification) -> EvidenceLevel:
    if v.external_verification and not v.external.mock:
        return EvidenceLevel.ISSUER_VERIFIED
    if v.cryptographic_verification:
        return EvidenceLevel.CRYPTOGRAPHIC
    if v.ocr_success and v.format_valid and not v.failed():
        return EvidenceLevel.DOCUMENT_ANALYSIS
    if v.format_valid:
        return EvidenceLevel.FORMAT_ONLY
    return EvidenceLevel.NONE


def risk_score(v: DocumentVerification) -> float:
    risk = 0.0
    risk += min(0.5, 0.25 * len(v.failed()))
    risk += min(0.2, 0.05 * sum(1 for c in v.checks if c.outcome == CheckOutcome.WARN))
    risk += 0.5 * v.tampering_score
    if v.identity_consistent is False:
        risk += 0.3
    if v.cryptographic_verification is False:
        risk = max(risk, 0.9)
    if v.external.identity_matched is False:
        risk += 0.3
    if v.tampering_detected:
        risk = max(risk, 0.85)
    if v.external_verification or v.cryptographic_verification:
        risk *= 0.5            # authoritative evidence lowers, never zeroes, residual risk
    return round(max(0.0, min(1.0, risk)), 3)


def decide(v: DocumentVerification) -> DocumentVerification:
    """Compute v.status / evidence_level / risk_score / summary from the evidence recorded in v."""
    v.tampering_detected = v.tampering_detected or v.tampering_score >= tamper_suspicious_threshold()
    v.evidence_level = evidence_level(v)
    v.risk_score = risk_score(v)

    suspicious = (
        v.tampering_detected
        or v.cryptographic_verification is False
        or v.identity_consistent is False
        or v.external.identity_matched is False
    )
    required = REQUIRED_PASS.get(v.document_type.upper(), ())
    authoritative = (
        (v.cryptographic_verification is True)
        or (v.external_verification is True and not v.external.mock)
    )

    if suspicious:
        v.status = DocStatus.SUSPICIOUS
        v.summary = "Signs of manipulation or inconsistent data were detected."
    elif v.failed():
        v.status = DocStatus.INVALID
        v.summary = "The document failed validation."
    elif v.unreadable or not v.document_detected:
        v.status = DocStatus.MANUAL_REVIEW_REQUIRED
        v.summary = "The document could not be read or identified reliably."
    elif authoritative and all(v.passed(c) for c in required):
        v.status = DocStatus.VALID
        v.summary = (
            "Confirmed by the issuer's digital signature." if v.cryptographic_verification
            else "Confirmed by an authoritative external source."
        )
    elif v.authority_unavailable:
        v.status = DocStatus.VERIFICATION_UNAVAILABLE
        v.summary = (
            "The document appears consistent, but authoritative verification was unavailable, "
            "so it has NOT been verified."
        )
    else:
        v.status = DocStatus.MANUAL_REVIEW_REQUIRED
        v.summary = "Authenticity could not be determined automatically."

    # Surface the reasons a human or the UI should see
    v.reasons = [c.detail or c.label for c in v.checks
                 if c.outcome in (CheckOutcome.FAIL, CheckOutcome.WARN) and (c.detail or c.label)]
    return v
