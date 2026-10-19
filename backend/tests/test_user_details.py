import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.verification import DocumentType, ExtractedFields
from services.kyc.user_details import compare_declared_details, parse_declared_type


def _compare(**kw):
    base = dict(
        declared_type=DocumentType.AADHAAR, detected_type=DocumentType.AADHAAR,
        full_name="Rahul Sharma", dob="15/08/1999",
        extracted=ExtractedFields(name="RAHUL SHARMA", dob="15/08/1999"),
    )
    base.update(kw)
    return compare_declared_details(**base)


@pytest.mark.parametrize("value,expected", [
    ("aadhaar", DocumentType.AADHAAR), (" Passport ", DocumentType.PASSPORT),
    ("citizenship", DocumentType.CITIZENSHIP), ("", None), ("unknown", None), ("college_id", None), ("nonsense", None),
])
def test_parse_declared_type(value, expected):
    assert parse_declared_type(value) == expected


def test_all_fields_agree():
    r = _compare()
    assert r["all_match"] is True and r["mismatches"] == []


def test_mismatches_are_reported():
    r = _compare(full_name="Someone Else", dob="01/01/2000", declared_type=DocumentType.PASSPORT)
    assert set(r["mismatches"]) == {"name", "dob", "document_type"} and "id_number" not in r
    assert r["all_match"] is False


def test_unreadable_or_missing_fields_are_not_mismatches():
    r = _compare(extracted=ExtractedFields(name=None, dob=None), detected_type=DocumentType.UNKNOWN)
    assert r["name"] is None and r["dob"] is None and r["document_type"] is None
    assert r["mismatches"] == [] and r["all_match"] is False    # nothing was comparable
    r = _compare(extracted=ExtractedFields(name="RAHUL SHARMA", dob=None))
    assert r["dob"] is None and r["all_match"] is True          # only the name was comparable
    r = _compare(full_name="", dob="", detected_type=DocumentType.UNKNOWN)
    assert r["all_match"] is False                                 # nothing compared → not "matched"


def test_result_contains_only_booleans():
    assert all(isinstance(v, (bool, type(None), list)) for v in _compare().values())


def test_upload_route_requires_document_type():
    from api.routes import document
    from tests.test_uploads_and_api import png_bytes

    app = FastAPI()
    app.include_router(document.router, prefix="/api")
    client = TestClient(app)
    files = {"file": ("id.png", png_bytes(), "image/png")}
    for bad in ("", "unknown", "nonsense"):
        r = client.post("/api/upload-document", data={"document_type": bad, "full_name": "A B"}, files=files)
        assert r.status_code == 422, bad
        assert "select a document type" in r.json()["detail"].lower()
    # missing the field entirely
    assert client.post("/api/upload-document", files=files).status_code == 422


# ── Name found in the raw OCR text / year-only DOB ───────────────────────────

def test_name_found_in_raw_ocr_text_when_parsed_name_is_garbage():
    r = _compare(full_name="Kirtan Shrestha", dob="01/01/2005",
                 extracted=ExtractedFields(name="Govemmenioklnd", dob="2005"),
                 ocr_text="Government of India Kirtan Shresiha DOB: 2005 MALE")
    assert r["name"] is True and r["dob"] is True


def test_name_not_in_text_is_a_mismatch_only_if_something_was_parsed():
    assert _compare(full_name="Kirtan Shrestha", extracted=ExtractedFields(name="Rohan Das"),
                    ocr_text="Rohan Das")["name"] is False
    assert _compare(full_name="Kirtan Shrestha", extracted=ExtractedFields(name=None),
                    ocr_text="nothing readable")["name"] is None


def test_year_only_dob():
    assert _compare(dob="19/11/2005", extracted=ExtractedFields(name="RAHUL SHARMA", dob="2005"))["dob"] is True
    assert _compare(dob="19/11/2004", extracted=ExtractedFields(name="RAHUL SHARMA", dob="2005"))["dob"] is False


def test_document_type_alone_is_not_a_match():
    """Nothing readable from the document → must not claim 'details match' just because the type agrees."""
    r = _compare(extracted=ExtractedFields(name=None, dob=None))
    assert r["document_type"] is True and r["name"] is None and r["dob"] is None
    assert r["all_match"] is False and r["unreadable"] is True
    r = _compare()
    assert r["all_match"] is True and r["unreadable"] is False
