import httpx
import pytest

from models.verification import DocumentType
from services.kyc.document_verification import verify_document
from services.kyc.documents.pan import detect_pan_candidates, pan_format_valid
from services.kyc.providers import registry
from services.kyc.providers.base import ErrorCategory, ProviderOutcome
from services.kyc.result import DocStatus

PAN_LINES = ["INCOME TAX DEPARTMENT", "GOVT. OF INDIA", "Permanent Account Number", "ABCPK1234F",
             "Name", "Rahul Kumar", "Date of Birth", "15/08/1990"]


async def run(ctx):
    return await verify_document(
        doc_type=ctx.doc_type, img=ctx.img, lines=ctx.lines, full_text=ctx.full_text, fields=ctx.fields,
        validation=ctx.validation, face_extracted=True)


def use_provider(monkeypatch, handler):
    monkeypatch.setenv("PAN_API_URL", "https://pan.example.test/verify")
    monkeypatch.setenv("PAN_API_KEY", "test-secret-key")
    registry._test_transports["PAN"] = httpx.MockTransport(handler)


# ── Format layer ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pan,ok", [("ABCPK1234F", True), ("ABCDE1234", False), ("1BCPK1234F", False),
                                    ("ABCXK1234F", False), ("abcpk1234f", True), ("", False)])
def test_pan_format(pan, ok):
    assert pan_format_valid(pan) is ok


def test_pan_candidates_repair_ocr_confusion():
    assert "ABCPK1234F" in detect_pan_candidates("PAN ABCPKI234F")   # I → 1


async def test_wrong_pan_format_is_invalid(make_ctx):
    ctx = make_ctx(DocumentType.PAN, ["INCOME TAX DEPARTMENT", "Permanent Account Number", "ABCDE12345", "Name", "Rahul Kumar"])
    v = await run(ctx)
    assert v.status == DocStatus.INVALID and v.format_valid is False


# ── Never "verified" from format/OCR alone ────────────────────────────────────

async def test_no_provider_configured_is_unavailable_not_verified(make_ctx):
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.format_valid is True
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE
    assert v.external_verification is None and v.external.outcome == "NOT_CONFIGURED"
    assert "EXTERNAL_VERIFICATION_UNAVAILABLE" in " ".join(v.reasons)


async def test_provider_match_is_valid(make_ctx, monkeypatch):
    use_provider(monkeypatch, lambda r: httpx.Response(200, json={"status": "VALID", "name": "RAHUL KUMAR", "dob": "1990-08-15"}))
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.status == DocStatus.VALID
    assert v.external_verification is True and v.external.identity_matched is True
    assert v.evidence_level.value == "issuer_verified"
    assert v.provider  # recorded server-side...
    assert "provider" not in v.model_dump()   # ...but never serialised to clients


async def test_provider_identity_mismatch_is_suspicious(make_ctx, monkeypatch):
    use_provider(monkeypatch, lambda r: httpx.Response(200, json={"status": "VALID", "name": "SOMEONE ELSE", "dob": "1970-01-01"}))
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.status == DocStatus.SUSPICIOUS


async def test_provider_says_not_found_is_invalid(make_ctx, monkeypatch):
    use_provider(monkeypatch, lambda r: httpx.Response(200, json={"status": "NOT_FOUND"}))
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.status == DocStatus.INVALID


@pytest.mark.parametrize("handler,category", [
    (lambda r: httpx.Response(401, json={}), "auth"),
    (lambda r: httpx.Response(403, json={}), "auth"),
    (lambda r: httpx.Response(429, json={}), "rate_limit"),
    (lambda r: httpx.Response(503, json={}), "provider_error"),
    (lambda r: httpx.Response(200, text="<html>not json</html>"), "malformed_response"),
    (lambda r: httpx.Response(200, json={"unexpected": 1}), "malformed_response"),
    (lambda r: httpx.Response(200, json=["a", "list"]), "malformed_response"),
    (lambda r: httpx.Response(200, json={"status": "WHAT"}), "malformed_response"),
])
async def test_provider_failures_never_become_verified(make_ctx, monkeypatch, handler, category):
    use_provider(monkeypatch, handler)
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE
    assert v.external.error_category == category
    assert v.external_verification is None


async def test_timeout_and_network_failure(make_ctx, monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    use_provider(monkeypatch, timeout)
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE and v.external.error_category == "timeout"
    use_provider(monkeypatch, down)
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.external.error_category == "network"


async def test_retry_on_transient_error(make_ctx, monkeypatch):
    calls = []

    def flaky(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"status": "VALID", "name": "Rahul Kumar"})

    monkeypatch.setenv("PAN_API_RETRIES", "1")
    use_provider(monkeypatch, flaky)
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert len(calls) == 2 and v.status == DocStatus.VALID


async def test_api_key_sent_only_in_header_and_never_in_result(make_ctx, monkeypatch):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "VALID", "name": "Rahul Kumar"})

    use_provider(monkeypatch, handler)
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert seen["auth"] == "Bearer test-secret-key" and "test-secret-key" not in seen["body"]
    assert "test-secret-key" not in v.model_dump_json()


# ── Mock provider ─────────────────────────────────────────────────────────────

async def test_mock_provider_is_never_genuine_verification(make_ctx, monkeypatch):
    monkeypatch.setenv("PAN_PROVIDER", "mock")
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.external.mock is True
    assert v.status != DocStatus.VALID and v.external_verification is None
    assert any("MOCK_VERIFICATION" in c.detail for c in v.checks)


async def test_mock_provider_disabled_in_production(make_ctx, monkeypatch):
    monkeypatch.setenv("PAN_PROVIDER", "mock")
    monkeypatch.setenv("APP_ENV", "production")
    assert registry.get_provider("PAN") is None
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.external.outcome == "NOT_CONFIGURED"


def test_provider_status_reports_no_secrets(monkeypatch):
    monkeypatch.setenv("PAN_API_URL", "https://x.test")
    monkeypatch.setenv("PAN_API_KEY", "shh")
    status = registry.provider_status()
    assert status["PAN"] == "configured" and status["PASSPORT"] == "not_configured"
    assert "shh" not in str(status)


async def test_provider_never_raises_into_workflow(make_ctx, monkeypatch):
    use_provider(monkeypatch, lambda r: httpx.Response(200, json={"status": "VALID"}))
    provider = registry.get_provider("PAN")

    async def boom(request):
        raise RuntimeError("bug in adapter")

    monkeypatch.setattr(type(provider), "verify", lambda self, req: boom(req))
    v = await run(make_ctx(DocumentType.PAN, PAN_LINES))
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE
