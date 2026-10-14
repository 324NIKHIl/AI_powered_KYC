"""
Provider interfaces. The KYC workflow only ever talks to these abstractions;
concrete providers (generic REST, mock, or any future vendor adapter) are chosen
by backend configuration (see registry.py), so swapping vendors never touches
the verification workflow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderOutcome(str, Enum):
    MATCH       = "MATCH"         # authoritative source confirms the record
    MISMATCH    = "MISMATCH"      # record exists but identity details differ
    NOT_FOUND   = "NOT_FOUND"     # authoritative source says the document/number is invalid
    UNAVAILABLE = "UNAVAILABLE"   # could not be determined — NEVER the same as verified


class ErrorCategory(str, Enum):
    NOT_CONFIGURED     = "not_configured"
    TIMEOUT            = "timeout"
    AUTH               = "auth"
    RATE_LIMIT         = "rate_limit"
    NETWORK            = "network"
    PROVIDER_ERROR     = "provider_error"
    MALFORMED_RESPONSE = "malformed_response"
    INVALID_REQUEST    = "invalid_request"


@dataclass
class ProviderResult:
    outcome: ProviderOutcome
    error_category: Optional[ErrorCategory] = None
    identity: dict[str, Any] = field(default_factory=dict)   # name / dob returned by the source
    mock: bool = False
    provider_name: str = ""

    @classmethod
    def unavailable(cls, category: ErrorCategory, name: str = "") -> "ProviderResult":
        return cls(ProviderOutcome.UNAVAILABLE, category, provider_name=name)


class DocumentVerificationProvider(ABC):
    """Verifies a document / identifier against an authoritative source."""

    kind: str = ""          # PAN | PASSPORT | DRIVING_LICENCE | CITIZENSHIP | EDUCATION
    name: str = "unknown"
    mock: bool = False

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def verify(self, request: dict[str, Any]) -> ProviderResult:
        """
        `request` carries normalised fields (document_number, name, dob, …).
        Implementations MUST NOT raise for provider/network problems — they return
        ProviderOutcome.UNAVAILABLE with an ErrorCategory — and MUST NOT log the
        request body or credentials.
        """


# Typed interfaces so call sites (and future vendor adapters) can be explicit.
class PANVerificationProvider(DocumentVerificationProvider):
    kind = "PAN"


class PassportVerificationProvider(DocumentVerificationProvider):
    kind = "PASSPORT"


class DrivingLicenceVerificationProvider(DocumentVerificationProvider):
    kind = "DRIVING_LICENCE"


class IdentityVerificationProvider(DocumentVerificationProvider):
    """Government identity records (citizenship certificates, national ID)."""
    kind = "CITIZENSHIP"


class EducationVerificationProvider(DocumentVerificationProvider):
    kind = "EDUCATION"
