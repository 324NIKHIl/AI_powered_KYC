"""
Development/testing provider. Every result is flagged `mock=True`
(MOCK_VERIFICATION) and the decision engine will never turn a mock result into
VERIFIED. The registry refuses to load it when APP_ENV=production.
"""

from __future__ import annotations

from typing import Any

from services.kyc.providers.base import ProviderOutcome, ProviderResult


class MockProviderMixin:
    name = "MOCK_VERIFICATION"
    mock = True

    @property
    def configured(self) -> bool:
        return True

    async def verify(self, request: dict[str, Any]) -> ProviderResult:
        number = str(request.get("document_number") or "").upper()
        if number.startswith("INVALID") or number.endswith("0000"):
            return ProviderResult(ProviderOutcome.NOT_FOUND, mock=True, provider_name=self.name)
        identity = {k: request[k] for k in ("name", "dob") if request.get(k)}
        return ProviderResult(ProviderOutcome.MATCH, identity=identity, mock=True, provider_name=self.name)
