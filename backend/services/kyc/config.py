"""
Backend-only configuration for the KYC verification layer.

Everything is read from environment variables at call time (not import time) so
tests and deployments can change it without re-importing modules. Secrets
(API keys) exist only here, on the server — they are never put in an API
response, never logged, and never sent to the React app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in ("production", "prod")


# Document kinds that have an external-provider slot, and their env prefix.
PROVIDER_PREFIX = {
    "PAN": "PAN",
    "PASSPORT": "PASSPORT",
    "DRIVING_LICENCE": "DL",
    "CITIZENSHIP": "CITIZENSHIP",
    "EDUCATION": "EDUCATION",
}


@dataclass(frozen=True)
class ProviderConfig:
    kind: str
    mode: str                   # none | generic | mock
    url: str = ""
    api_key: str = field(default="", repr=False)   # repr=False: never printed by accident
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    timeout_s: float = 10.0
    retries: int = 1
    status_key: str = "status"
    valid_values: tuple[str, ...] = ("VALID", "VERIFIED", "SUCCESS", "TRUE", "ACTIVE")
    not_found_values: tuple[str, ...] = ("INVALID", "NOT_FOUND", "FAILED", "FALSE")
    name_key: str = "name"
    dob_key: str = "dob"

    @property
    def configured(self) -> bool:
        if self.mode == "mock":
            return True
        return self.mode == "generic" and bool(self.url and self.api_key)


def provider_config(kind: str) -> ProviderConfig:
    prefix = PROVIDER_PREFIX[kind]
    url = os.getenv(f"{prefix}_API_URL", "").strip()
    key = os.getenv(f"{prefix}_API_KEY", "").strip()
    mode = os.getenv(f"{prefix}_PROVIDER", "").strip().lower()
    if not mode:
        mode = "generic" if (url and key) else "none"
    if mode == "mock" and is_production():
        mode = "none"   # a mock may never stand in for verification in production
    if mode not in ("none", "generic", "mock"):
        mode = "none"
    csv = lambda name, default: tuple(  # noqa: E731
        v.strip().upper() for v in os.getenv(name, ",".join(default)).split(",") if v.strip()
    )
    d = ProviderConfig(kind=kind, mode=mode)
    return ProviderConfig(
        kind=kind,
        mode=mode,
        url=url,
        api_key=key,
        auth_header=os.getenv(f"{prefix}_API_AUTH_HEADER", d.auth_header),
        auth_scheme=os.getenv(f"{prefix}_API_AUTH_SCHEME", d.auth_scheme),
        timeout_s=_float(f"{prefix}_API_TIMEOUT_S", d.timeout_s),
        retries=max(0, min(3, _int(f"{prefix}_API_RETRIES", d.retries))),
        status_key=os.getenv(f"{prefix}_API_STATUS_KEY", d.status_key),
        valid_values=csv(f"{prefix}_API_VALID_VALUES", d.valid_values),
        not_found_values=csv(f"{prefix}_API_NOT_FOUND_VALUES", d.not_found_values),
        name_key=os.getenv(f"{prefix}_API_NAME_KEY", d.name_key),
        dob_key=os.getenv(f"{prefix}_API_DOB_KEY", d.dob_key),
    )


# ── Face / liveness / deepfake thresholds (all documented in .env.example) ────

def face_match_threshold() -> float:
    """Cosine similarity at/above which faces MATCH (ArcFace, aligned, flip-TTA)."""
    return _float("FACE_SIMILARITY_THRESHOLD", _float("FACE_MATCH_THRESHOLD", 0.32))


def face_no_match_threshold() -> float:
    """Below this the faces clearly differ (NO_MATCH). Between this and the match threshold: UNCERTAIN."""
    return min(_float("FACE_NO_MATCH_THRESHOLD", 0.22), face_match_threshold())


def liveness_fail_threshold() -> float:
    """Presentation-attack score at/above which liveness FAILS."""
    return _float("LIVENESS_ATTACK_THRESHOLD", 0.65)


def liveness_uncertain_threshold() -> float:
    return min(_float("LIVENESS_UNCERTAIN_THRESHOLD", 0.40), liveness_fail_threshold())


def deepfake_high_threshold() -> float:
    return _float("DEEPFAKE_HIGH_RISK_THRESHOLD", 0.70)


def deepfake_review_threshold() -> float:
    return min(_float("DEEPFAKE_REVIEW_THRESHOLD", 0.45), deepfake_high_threshold())


def tamper_suspicious_threshold() -> float:
    return _float("TAMPER_SUSPICIOUS_THRESHOLD", 0.80)


def max_upload_bytes() -> int:
    return _int("MAX_FILE_SIZE_MB", 10) * 1024 * 1024


def aadhaar_certificate_path() -> str:
    return os.getenv("AADHAAR_CERTIFICATE_PATH", "").strip()
