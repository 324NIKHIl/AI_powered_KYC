from datetime import date, timedelta

import httpx
import pytest

from models.verification import DocumentType
from services.kyc.document_verification import verify_document
from services.kyc.documents.driving_licence import validate_licence_number
from services.kyc.providers import registry
from services.kyc.result import DocStatus
from utils.validators import detect_document_type


async def run(ctx, face=True):
    return await verify_document(
        doc_type=ctx.doc_type, img=ctx.img, lines=ctx.lines, full_text=ctx.full_text, fields=ctx.fields,
        validation=ctx.validation, face_extracted=face)


def provider(monkeypatch, kind_prefix, kind, handler):
    monkeypatch.setenv(f"{kind_prefix}_API_URL", "https://x.test/v")
    monkeypatch.setenv(f"{kind_prefix}_API_KEY", "k")
    registry._test_transports[kind] = httpx.MockTransport(handler)


# ── Driving licence ───────────────────────────────────────────────────────────

def dl_lines(number="MH12 20110012345", valid=None):
    valid = valid or (date.today() + timedelta(days=900)).strftime("%d-%m-%Y")
    return ["Union of India", "Driving Licence", f"DL No. {number}", "Name Rahul Kumar",
            "DOB 15-08-1990", "DOI 10-03-2011", f"Valid Till {valid}"]


@pytest.mark.parametrize("number,ok", [("MH12 20110012345", True), ("MH-12-2011-0012345", True),
                                       ("XX12 20110012345", False), ("MH12 18000012345", False), ("MH1220110012", False)])
def test_licence_number_structure(number, ok):
    assert validate_licence_number(number.replace(" ", "").replace("-", ""))[0] is ok


async def test_dl_valid_format_without_provider_unavailable(make_ctx):
    v = await run(make_ctx(DocumentType.DRIVING_LICENCE, dl_lines()))
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE and v.format_valid is True
    assert v.extracted["issuing_state"] == "Maharashtra"


async def test_dl_expired_is_invalid(make_ctx):
    v = await run(make_ctx(DocumentType.DRIVING_LICENCE, dl_lines(valid="01-01-2015")))
    assert v.status == DocStatus.INVALID


async def test_dl_bad_state_code_invalid(make_ctx):
    v = await run(make_ctx(DocumentType.DRIVING_LICENCE, dl_lines(number="ZZ12 20110012345")))
    assert v.status in (DocStatus.INVALID, DocStatus.MANUAL_REVIEW_REQUIRED)
    assert v.status != DocStatus.VALID


async def test_dl_provider_match_valid(make_ctx, monkeypatch):
    provider(monkeypatch, "DL", "DRIVING_LICENCE",
             lambda r: httpx.Response(200, json={"status": "ACTIVE", "name": "Rahul Kumar", "dob": "1990-08-15"}))
    v = await run(make_ctx(DocumentType.DRIVING_LICENCE, dl_lines()))
    assert v.status == DocStatus.VALID


# ── Citizenship ───────────────────────────────────────────────────────────────

NP_LINES = ["Government of Nepal", "Citizenship Certificate", "Certificate No. 27-01-71-01234",
            "Full Name Sita Sharma", "Date of Birth 2050/05/12", "District Kathmandu",
            "Issued on 2068/03/10", "District Administration Office Kathmandu"]


async def test_nepal_citizenship_appears_valid_but_not_government_verified(make_ctx):
    ctx = make_ctx(DocumentType.CITIZENSHIP, NP_LINES)
    v = await run(ctx)
    assert v.format_valid is True and v.passed("cz_number") and v.passed("cz_authority")
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE      # never VALID without an authoritative source
    assert v.evidence_level.value == "document_analysis"
    assert v.extracted["country"] == "Nepal"


async def test_nepal_citizenship_implausible_year_invalid(make_ctx):
    lines = [l.replace("2050/05/12", "3050/05/12") for l in NP_LINES]
    v = await run(make_ctx(DocumentType.CITIZENSHIP, lines))
    assert v.status == DocStatus.INVALID


async def test_unsupported_country_requires_manual_review(make_ctx):
    v = await run(make_ctx(DocumentType.CITIZENSHIP, ["Certificate of Citizenship", "Republic of Atlantis", "No. 12345"]))
    assert v.status == DocStatus.MANUAL_REVIEW_REQUIRED


async def test_citizenship_government_provider_confirms(make_ctx, monkeypatch):
    provider(monkeypatch, "CITIZENSHIP", "CITIZENSHIP", lambda r: httpx.Response(200, json={"status": "VALID", "name": "Sita Sharma"}))
    v = await run(make_ctx(DocumentType.CITIZENSHIP, NP_LINES))
    assert v.status == DocStatus.VALID and v.evidence_level.value == "issuer_verified"


# ── Education ─────────────────────────────────────────────────────────────────

EDU = ["Central Board of Secondary Education", "Senior School Certificate Examination Class XII", "Year 2012",
       "Roll No. 1234567", "Name of Student Rahul Kumar", "ENGLISH 100 85", "PHYSICS 100 78", "CHEMISTRY 100 80",
       "MATHEMATICS 100 92", "Total 335", "Percentage 83.75"]


async def test_education_extracted_but_not_verified(make_ctx):
    ctx = make_ctx(DocumentType.EDUCATION, EDU)
    assert detect_document_type(ctx.full_text) == DocumentType.EDUCATION
    v = await run(ctx)
    assert v.passed("edu_roll")
    assert v.extracted["board"].startswith("Central Board") and v.extracted["level"] == "12th"
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE
    assert any(c.id == "edu_not_verified" for c in v.checks)


async def test_education_inconsistent_total_is_invalid(make_ctx):
    lines = [l.replace("Total 335", "Total 395").replace("Percentage 83.75", "Percentage 98.75") for l in EDU]
    v = await run(make_ctx(DocumentType.EDUCATION, lines))
    assert v.status == DocStatus.INVALID


async def test_education_marks_above_maximum_invalid(make_ctx):
    lines = [l.replace("ENGLISH 100 85", "ENGLISH 80 95") for l in EDU]
    # 80/95 is read as max 95 / obtained 80 by design (column order varies) → not an arithmetic violation
    v = await run(make_ctx(DocumentType.EDUCATION, [l for l in lines if "Total" not in l and "Percentage" not in l]))
    assert v.status != DocStatus.VALID


async def test_education_provider_confirms(make_ctx, monkeypatch):
    provider(monkeypatch, "EDUCATION", "EDUCATION", lambda r: httpx.Response(200, json={"status": "VERIFIED", "name": "Rahul Kumar"}))
    v = await run(make_ctx(DocumentType.EDUCATION, EDU))
    assert v.status == DocStatus.VALID


# ── Detection ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Driving Licence Union of India", DocumentType.DRIVING_LICENCE),
    ("Citizenship Certificate Nepal", DocumentType.CITIZENSHIP),
    ("Statement of Marks Board of Secondary Education", DocumentType.EDUCATION),
    ("INCOME TAX DEPARTMENT ABCPK1234F", DocumentType.PAN),
    ("Government of India Aadhaar 4017 1397 4861", DocumentType.AADHAAR),
    ("P<INDSHARMA<<RAHUL<KUMAR<<<<<<<<<<<<<<<<<<<<<<", DocumentType.PASSPORT),
    ("Company Pvt Ltd Panchayat", DocumentType.UNKNOWN),
])
def test_document_type_detection(text, expected):
    assert detect_document_type(text) == expected
