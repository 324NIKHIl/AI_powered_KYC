"""
Generic REST provider: POSTs the normalised request as JSON to a configured
endpoint and maps a JSON response to a ProviderResult.

Request:   POST <X_API_URL>   {"document_type": "...", "document_number": "...", "name": "...", "dob": "...", ...}
Auth:      <X_API_AUTH_HEADER>: <X_API_AUTH_SCHEME> <X_API_KEY>   (defaults to "Authorization: Bearer <key>")
Response:  JSON object; status read from X_API_STATUS_KEY (dot path allowed), compared with
           X_API_VALID_VALUES / X_API_NOT_FOUND_VALUES; optional name/dob from X_API_NAME_KEY / X_API_DOB_KEY.

A vendor with a different contract gets a small adapter subclass (override
`build_body` / `parse`) — the KYC workflow itself does not change.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from services.kyc.config import ProviderConfig
from services.kyc.providers.base import (
    DocumentVerificationProvider,
    ErrorCategory,
    ProviderOutcome,
    ProviderResult,
)

logger = logging.getLogger(__name__)


def _dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return None
    return data


class GenericRestMixin:
    """Mixed into the typed provider interfaces by the registry."""

    cfg: ProviderConfig
    name = "generic-rest"
    mock = False
    # Injectable for tests (httpx.MockTransport)
    _transport: Optional[httpx.AsyncBaseTransport] = None

    def __init__(self, cfg: ProviderConfig, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.cfg = cfg
        if transport is not None:
            self._transport = transport

    @property
    def configured(self) -> bool:
        return self.cfg.configured

    def build_body(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"document_type": self.kind, **{k: v for k, v in request.items() if v not in (None, "")}}  # type: ignore[attr-defined]

    def parse(self, payload: Any) -> ProviderResult:
        if not isinstance(payload, dict):
            return ProviderResult.unavailable(ErrorCategory.MALFORMED_RESPONSE, self.name)
        raw = _dig(payload, self.cfg.status_key)
        if raw is None:
            return ProviderResult.unavailable(ErrorCategory.MALFORMED_RESPONSE, self.name)
        status = str(raw).strip().upper()
        identity = {}
        for key, field in ((self.cfg.name_key, "name"), (self.cfg.dob_key, "dob")):
            value = _dig(payload, key)
            if isinstance(value, (str, int)) and str(value).strip():
                identity[field] = str(value).strip()
        if status in self.cfg.valid_values:
            return ProviderResult(ProviderOutcome.MATCH, identity=identity, provider_name=self.name)
        if status in self.cfg.not_found_values:
            return ProviderResult(ProviderOutcome.NOT_FOUND, identity=identity, provider_name=self.name)
        return ProviderResult.unavailable(ErrorCategory.MALFORMED_RESPONSE, self.name)

    async def verify(self, request: dict[str, Any]) -> ProviderResult:
        if not self.configured:
            return ProviderResult.unavailable(ErrorCategory.NOT_CONFIGURED, self.name)

        headers = {
            self.cfg.auth_header: f"{self.cfg.auth_scheme} {self.cfg.api_key}".strip(),
            "Accept": "application/json",
        }
        result = ProviderResult.unavailable(ErrorCategory.NETWORK, self.name)
        for attempt in range(self.cfg.retries + 1):
            result = await self._once(headers, request)
            retryable = result.error_category in (
                ErrorCategory.TIMEOUT, ErrorCategory.NETWORK, ErrorCategory.PROVIDER_ERROR,
            )
            if not retryable:
                break
            if attempt < self.cfg.retries:
                await asyncio.sleep(0.3 * (attempt + 1))
        # Category only — never the URL, key, request or response body
        logger.info(
            "provider kind=%s outcome=%s error=%s",
            self.kind,  # type: ignore[attr-defined]
            result.outcome.value,
            result.error_category.value if result.error_category else None,
        )
        return result

    async def _once(self, headers: dict[str, str], request: dict[str, Any]) -> ProviderResult:
        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout_s, transport=self._transport) as client:
                response = await client.post(self.cfg.url, json=self.build_body(request), headers=headers)
        except httpx.TimeoutException:
            return ProviderResult.unavailable(ErrorCategory.TIMEOUT, self.name)
        except (httpx.NetworkError, httpx.ProxyError):
            return ProviderResult.unavailable(ErrorCategory.NETWORK, self.name)
        except httpx.HTTPError:
            return ProviderResult.unavailable(ErrorCategory.NETWORK, self.name)

        code = response.status_code
        if code in (401, 403):
            return ProviderResult.unavailable(ErrorCategory.AUTH, self.name)
        if code == 429:
            return ProviderResult.unavailable(ErrorCategory.RATE_LIMIT, self.name)
        if code in (400, 422):
            return ProviderResult.unavailable(ErrorCategory.INVALID_REQUEST, self.name)
        if code >= 500 or code == 404:
            return ProviderResult.unavailable(ErrorCategory.PROVIDER_ERROR, self.name)
        if code >= 300:
            return ProviderResult.unavailable(ErrorCategory.PROVIDER_ERROR, self.name)
        try:
            payload = response.json()
        except ValueError:
            return ProviderResult.unavailable(ErrorCategory.MALFORMED_RESPONSE, self.name)
        try:
            return self.parse(payload)
        except Exception:  # defensive: a vendor adapter bug must not crash the KYC flow
            logger.exception("provider response parse failed kind=%s", self.kind)  # type: ignore[attr-defined]
            return ProviderResult.unavailable(ErrorCategory.MALFORMED_RESPONSE, self.name)
