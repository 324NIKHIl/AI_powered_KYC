"""Runs the configured external provider and folds its result into a DocumentVerification."""

from __future__ import annotations

from typing import Any, Optional

from services.kyc.providers.base import ErrorCategory, ProviderOutcome
from services.kyc.providers.registry import get_provider
from services.kyc.result import CheckOutcome, DocumentVerification
from services.kyc.text_utils import dobs_match, find_dates, fuzzy_contains, names_match, normalise_name, parse_date

_ERROR_TEXT = {
    ErrorCategory.NOT_CONFIGURED: "No verification provider is configured",
    ErrorCategory.TIMEOUT: "The verification provider timed out",
    ErrorCategory.AUTH: "The verification provider rejected our credentials",
    ErrorCategory.RATE_LIMIT: "The verification provider is rate-limiting requests",
    ErrorCategory.NETWORK: "Could not reach the verification provider",
    ErrorCategory.PROVIDER_ERROR: "The verification provider returned an error",
    ErrorCategory.MALFORMED_RESPONSE: "The verification provider returned an unreadable response",
    ErrorCategory.INVALID_REQUEST: "The verification provider could not process the request",
}


async def run_external_verification(
    v: DocumentVerification,
    kind: str,
    request: dict[str, Any],
    *,
    label: str,
    expected_name: Optional[str] = None,
    expected_dob: Optional[str] = None,
    document_text: str = "",
) -> None:
    """
    Mutates `v`: fills v.external, adds the 'external' (+ 'external_identity') checks,
    and sets v.authority_unavailable when no genuine verification could be obtained.
    A failed/unavailable provider is never reported as verified.
    """
    provider = get_provider(kind)
    if provider is None:
        v.external.configured = False
        v.external.outcome = "NOT_CONFIGURED"
        v.external.error_category = ErrorCategory.NOT_CONFIGURED.value
        v.authority_unavailable = True
        v.add("external", label, CheckOutcome.WARN,
              "EXTERNAL_VERIFICATION_UNAVAILABLE — no provider configured; only local validation was performed")
        return

    v.provider = provider.name
    v.external.configured = True
    v.external.attempted = True
    v.external.mock = provider.mock

    try:
        result = await provider.verify(request)
    except Exception:  # a provider bug must never crash the KYC workflow
        from services.kyc.providers.base import ProviderResult
        result = ProviderResult.unavailable(ErrorCategory.PROVIDER_ERROR, provider.name)

    v.external.mock = result.mock or provider.mock
    v.external.outcome = result.outcome.value
    v.external.error_category = result.error_category.value if result.error_category else None

    if result.outcome == ProviderOutcome.UNAVAILABLE:
        v.authority_unavailable = True
        cat = result.error_category or ErrorCategory.PROVIDER_ERROR
        v.add("external", label, CheckOutcome.WARN,
              f"EXTERNAL_VERIFICATION_UNAVAILABLE — {_ERROR_TEXT.get(cat, 'verification failed')}")
        return

    if result.outcome == ProviderOutcome.NOT_FOUND:
        v.add("external", label, CheckOutcome.FAIL, "The authoritative source does not recognise this document")
        return

    # MATCH / MISMATCH → compare the identity the source returned with what we read
    # OCR field parsing is imperfect, so a returned identity also counts as consistent when it
    # is plainly printed somewhere on the document (the parsed field was merely mis-extracted).
    name_ok = dob_ok = None
    returned_name, returned_dob = result.identity.get("name"), result.identity.get("dob")
    if returned_name and (expected_name or document_text):
        tokens = [t for t in normalise_name(returned_name).split() if len(t) > 1]
        name_ok = bool(expected_name and names_match(returned_name, expected_name)) or bool(
            document_text and tokens and all(fuzzy_contains(document_text, t, 0.85) for t in tokens)
        )
    if returned_dob and (expected_dob or document_text):
        parsed = parse_date(returned_dob)
        dob_ok = bool(expected_dob and dobs_match(returned_dob, expected_dob)) or bool(
            parsed and document_text and parsed in find_dates(document_text)
        )
    compared = [x for x in (name_ok, dob_ok) if x is not None]
    v.external.identity_matched = all(compared) if compared else None

    if result.outcome == ProviderOutcome.MISMATCH or v.external.identity_matched is False:
        v.external.identity_matched = False
        v.add("external", label, CheckOutcome.FAIL, "The record exists but its details differ from the document")
        v.add("external_identity", "Identity details match the record", CheckOutcome.FAIL,
              "Name/date of birth returned by the source do not match the document")
        return

    if v.external.mock:
        v.authority_unavailable = True   # a mock is never genuine verification
        v.add("external", label, CheckOutcome.INFO, "MOCK_VERIFICATION — development provider; not a genuine verification")
        return

    v.external_verification = True
    v.add("external", label, CheckOutcome.PASS, "Confirmed by the authoritative source")
    if v.external.identity_matched:
        v.add("external_identity", "Identity details match the record", CheckOutcome.PASS)
    else:
        v.add("external_identity", "Identity details match the record", CheckOutcome.SKIP,
              "The source did not return name/date of birth to compare")
