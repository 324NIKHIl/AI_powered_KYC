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
