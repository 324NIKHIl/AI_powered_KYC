"""
Unified, evidence-based verification result shared by every document type.

The central idea: "I read this document" (OCR) is not "this document is authentic".
Every verifier records *which evidence layers actually ran* in `checks`, and the
decision engine (engine.py) only reaches VALID when authoritative evidence exists
(a verified cryptographic signature, or a successful non-mock issuer/provider lookup).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocStatus(str, Enum):
    VALID                    = "VALID"
    INVALID                  = "INVALID"
    SUSPICIOUS               = "SUSPICIOUS"
    VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"
    MANUAL_REVIEW_REQUIRED   = "MANUAL_REVIEW_REQUIRED"


class CheckOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"      # could not complete / needs a human
    SKIP = "skip"      # layer did not apply or no data
    INFO = "info"


class EvidenceLevel(str, Enum):
    """The strongest evidence obtained — never overstated."""
    NONE             = "none"              # nothing usable
    FORMAT_ONLY      = "format_only"       # structure/regex only — proves nothing about authenticity
    DOCUMENT_ANALYSIS = "document_analysis"  # OCR + consistency + image analysis (document "appears valid")
    CRYPTOGRAPHIC    = "cryptographic"     # issuer signature verified (Aadhaar QR, MRZ is NOT this)
    ISSUER_VERIFIED  = "issuer_verified"   # authoritative external source confirmed the record


class Check(BaseModel):
    id: str
    label: str
    outcome: CheckOutcome
    detail: str = ""


class ExternalVerification(BaseModel):
    """What the external provider layer did. Provider internals are never exposed."""
    attempted: bool = False
    configured: bool = False
    # MATCH | MISMATCH | NOT_FOUND | UNAVAILABLE | NOT_CONFIGURED
    outcome: str = "NOT_CONFIGURED"
    error_category: Optional[str] = None   # timeout | auth | rate_limit | network | provider_error | malformed_response
    identity_matched: Optional[bool] = None
    mock: bool = False                     # MOCK_VERIFICATION — never counts as genuine verification


class DocumentVerification(BaseModel):
    document_type: str
    document_detected: bool = False
    ocr_success: bool = False
    format_valid: Optional[bool] = None
    # True = signature verified, False = signature invalid, None = not applicable / not performed
    cryptographic_verification: Optional[bool] = None
    external_verification: Optional[bool] = None   # True only for a genuine (non-mock) provider MATCH
    external: ExternalVerification = Field(default_factory=ExternalVerification)
    identity_consistent: Optional[bool] = None     # cross-source data agreement (OCR vs QR/MRZ/provider)
    tampering_detected: bool = False
    tampering_score: float = 0.0
    # An authoritative source/key is required but could not be used (provider down or not
    # configured, UIDAI certificate missing). Maps to VERIFICATION_UNAVAILABLE, never VERIFIED.
    authority_unavailable: bool = False
    # Image too poor / text unreadable to judge — maps to MANUAL_REVIEW_REQUIRED
    unreadable: bool = False
    risk_score: float = 0.0
    evidence_level: EvidenceLevel = EvidenceLevel.NONE
    status: DocStatus = DocStatus.MANUAL_REVIEW_REQUIRED
    checks: list[Check] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    summary: str = ""
    # Parsed, document-specific fields shown to the user (identifiers are masked)
    extracted: dict[str, Any] = Field(default_factory=dict)
    # Internal: provider name kept for the audit record only, never serialised to clients
    provider: Optional[str] = Field(default=None, exclude=True)
    processing_ms: Optional[int] = None

    # ── helpers used by verifiers ─────────────────────────────────────────────
    def add(self, id: str, label: str, outcome: CheckOutcome, detail: str = "") -> Check:
        check = Check(id=id, label=label, outcome=outcome, detail=detail)
        self.checks.append(check)
        return check

    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.outcome == CheckOutcome.FAIL]

    def passed(self, id: str) -> bool:
        return any(c.id == id and c.outcome == CheckOutcome.PASS for c in self.checks)


def mask_identifier(value: Optional[str], keep: int = 4) -> Optional[str]:
    """Mask all but the last `keep` characters of an identifier (PAN, passport no., …)."""
    if not value:
        return None
    value = str(value)
    if len(value) <= keep:
        return "X" * len(value)
    return "X" * (len(value) - keep) + value[-keep:]


def safe_dump(v: DocumentVerification) -> dict[str, Any]:
    return v.model_dump(mode="json")
