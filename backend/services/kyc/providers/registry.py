"""Selects the configured provider for each document kind."""

from __future__ import annotations

from typing import Optional

import httpx

from services.kyc.config import PROVIDER_PREFIX, provider_config
from services.kyc.providers.base import (
    DocumentVerificationProvider,
    DrivingLicenceVerificationProvider,
    EducationVerificationProvider,
    IdentityVerificationProvider,
    PANVerificationProvider,
    PassportVerificationProvider,
)
from services.kyc.providers.generic_rest import GenericRestMixin
from services.kyc.providers.mock import MockProviderMixin

_INTERFACES: dict[str, type[DocumentVerificationProvider]] = {
    "PAN": PANVerificationProvider,
    "PASSPORT": PassportVerificationProvider,
    "DRIVING_LICENCE": DrivingLicenceVerificationProvider,
    "CITIZENSHIP": IdentityVerificationProvider,
    "EDUCATION": EducationVerificationProvider,
}

_GENERIC = {k: type(f"GenericRest{k.title()}Provider", (GenericRestMixin, i), {}) for k, i in _INTERFACES.items()}
_MOCK = {k: type(f"Mock{k.title()}Provider", (MockProviderMixin, i), {}) for k, i in _INTERFACES.items()}

# Tests can inject a transport per kind without touching the network.
_test_transports: dict[str, httpx.AsyncBaseTransport] = {}


def get_provider(kind: str) -> Optional[DocumentVerificationProvider]:
    """The provider selected by backend config for `kind`, or None when none is configured."""
    if kind not in PROVIDER_PREFIX:
        return None
    cfg = provider_config(kind)
    if cfg.mode == "mock":
        return _MOCK[kind]()
    if cfg.mode == "generic" and cfg.configured:
        return _GENERIC[kind](cfg, _test_transports.get(kind))
    return None


def provider_status() -> dict[str, str]:
    """Which kinds have an external provider (booleans only — nothing sensitive)."""
    out = {}
    for kind in PROVIDER_PREFIX:
        p = get_provider(kind)
        out[kind] = "mock" if p and p.mock else ("configured" if p else "not_configured")
    return out
