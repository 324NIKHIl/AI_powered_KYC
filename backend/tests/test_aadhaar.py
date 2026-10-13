"""Aadhaar Secure QR: real RSA-SHA256 signing/verification against a locally generated 'UIDAI' certificate."""

import datetime
import gzip

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from models.verification import AadhaarQrResult, DocumentType, QrSignatureStatus
from services import aadhaar_qr_service as qrs
from services.kyc import engine
from services.kyc.document_verification import verify_document
from services.kyc.documents import aadhaar
from services.kyc.result import DocStatus

V2_FIELDS = ["V2", "0", "56782026010112000000", "Rahul Kumar", "15-08-1990", "M", "S/O Mohan Kumar", "Pune", "", "12",
             "Kothrud", "411038", "Kothrud", "Maharashtra", "MG Road", "Pune", "Pune", "5678"]


def make_cert(tmp_path, common_name="UIDAI Secure QR"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    path = tmp_path / "uidai.cer"
    path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
    return key, path


def build_qr(key, fields=V2_FIELDS, tamper=False) -> str:
    signed = b"\xff".join(f.encode("iso-8859-1") for f in fields) + b"\xff"
    sig = key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    if tamper:
        signed = signed.replace(b"Rahul Kumar", b"Rohit Kumar")     # edit the data, keep the old signature
    blob = gzip.compress(signed + sig)
    return str(int.from_bytes(blob, "big"))


@pytest.fixture
def cert_dir(tmp_path, monkeypatch):
    key, _ = make_cert(tmp_path)
    monkeypatch.setattr(qrs, "UIDAI_CERT_DIR", str(tmp_path))
    monkeypatch.setattr(qrs, "UPLOAD_DIR", str(tmp_path / "up"))
    return key


def ocr_fields(name="Rahul Kumar", dob="15/08/1990", last4="5678"):
    from models.verification import ExtractedFields, FieldValidation
    return (ExtractedFields(name=name, dob=dob, gender="Male", id_number="2345 6789 " + last4),
            FieldValidation(name=True, dob=True, id_number=True))


def test_valid_signature_verifies(cert_dir):
    r = qrs._process_secure(build_qr(cert_dir), "t", *ocr_fields())
    assert r.signature_status == QrSignatureStatus.VERIFIED and not r.tamper_flags
    assert r.fields["name"] == "Rahul Kumar"


def test_modified_qr_data_fails_signature(cert_dir):
    r = qrs._process_secure(build_qr(cert_dir, tamper=True), "t", *ocr_fields())
    assert r.signature_status == QrSignatureStatus.INVALID and r.tamper_flags


def test_qr_signed_by_untrusted_key_is_invalid(cert_dir):
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    r = qrs._process_secure(build_qr(attacker), "t", *ocr_fields())
    assert r.signature_status == QrSignatureStatus.INVALID


def test_no_certificate_configured_is_unverified(tmp_path, monkeypatch):
    key, path = make_cert(tmp_path)
    path.unlink()
    monkeypatch.setattr(qrs, "UIDAI_CERT_DIR", str(tmp_path))
    monkeypatch.setattr(qrs, "UPLOAD_DIR", str(tmp_path / "up"))
    r = qrs._process_secure(build_qr(key), "t", *ocr_fields())
    assert r.signature_status == QrSignatureStatus.UNVERIFIED


def test_certificate_path_env(tmp_path, monkeypatch):
    key, path = make_cert(tmp_path)
    other = tmp_path / "empty"
    other.mkdir()
    monkeypatch.setattr(qrs, "UIDAI_CERT_DIR", str(other))
    monkeypatch.setattr(qrs, "UPLOAD_DIR", str(tmp_path / "up"))
    monkeypatch.setenv("AADHAAR_CERTIFICATE_PATH", str(path))
    assert qrs._process_secure(build_qr(key), "t", *ocr_fields()).signature_status == QrSignatureStatus.VERIFIED


def test_corrupted_qr_is_rejected():
    with pytest.raises(ValueError):
        qrs.parse_secure_qr("123456789" * 40)
    with pytest.raises(ValueError):
        qrs.parse_secure_qr("12ab")


def test_decompression_bomb_is_refused():
    bomb = gzip.compress(b"\x00" * 30_000_000)
    with pytest.raises(ValueError):
        qrs._decompress(bomb)


def test_staging_certificate_is_not_trusted(tmp_path, monkeypatch):
    key, _ = make_cert(tmp_path, common_name="UIDAI Staging Secure QR")
    monkeypatch.setattr(qrs, "UIDAI_CERT_DIR", str(tmp_path))
    monkeypatch.setattr(qrs, "UPLOAD_DIR", str(tmp_path / "up"))
    assert qrs._process_secure(build_qr(key), "t", *ocr_fields()).signature_status == QrSignatureStatus.UNVERIFIED


# ── From QR result to document status ─────────────────────────────────────────

async def run_doc(make_ctx, qr):
    ctx = make_ctx(DocumentType.AADHAAR, ["Government of India", "Aadhaar", "Rahul Kumar", "DOB: 15/08/1990",
                                          "Male", "2345 6789 5678"], qr=qr)
    return await verify_document(doc_type=ctx.doc_type, img=ctx.img, lines=ctx.lines, full_text=ctx.full_text,
                                 fields=ctx.fields, validation=ctx.validation, face_extracted=True, aadhaar_qr=qr)


def qr_result(status, checks=None, found=True, flags=None):
    return AadhaarQrResult(found=found, qr_format="secure_v2", signature_status=status,
                           field_checks=checks or {"name": "match", "dob": "match", "gender": "match", "aadhaar_last4": "match"},
                           tamper_flags=flags or [])


async def test_verified_signature_and_consistent_data_is_valid(make_ctx):
    v = await run_doc(make_ctx, qr_result(QrSignatureStatus.VERIFIED))
    assert v.status == DocStatus.VALID and v.cryptographic_verification is True
    assert v.evidence_level.value == "cryptographic"
    assert v.passed("qr_detected") and v.passed("qr_decoded") and v.passed("qr_signature") \
        and v.passed("qr_certificate") and v.passed("qr_consistent")


async def test_invalid_signature_is_suspicious(make_ctx):
    v = await run_doc(make_ctx, qr_result(QrSignatureStatus.INVALID))
    assert v.status == DocStatus.SUSPICIOUS and v.cryptographic_verification is False


async def test_valid_signature_but_card_data_differs_is_suspicious(make_ctx):
    v = await run_doc(make_ctx, qr_result(QrSignatureStatus.VERIFIED, {"name": "mismatch", "dob": "match"}))
    assert v.status == DocStatus.SUSPICIOUS and v.identity_consistent is False


async def test_valid_signature_but_nothing_to_compare_is_not_valid(make_ctx):
    # A genuine QR pasted on someone else's card must not pass: the printed data was never tied to it
    v = await run_doc(make_ctx, qr_result(QrSignatureStatus.VERIFIED, {"name": "unavailable", "dob": "unavailable"}))
    assert v.status != DocStatus.VALID


async def test_qr_present_but_signature_unchecked_is_unavailable(make_ctx):
    v = await run_doc(make_ctx, qr_result(QrSignatureStatus.UNVERIFIED))
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE and v.cryptographic_verification is None


async def test_legacy_unsigned_qr_is_manual_review(make_ctx):
    v = await run_doc(make_ctx, qr_result(QrSignatureStatus.UNSIGNED))
    assert v.status == DocStatus.MANUAL_REVIEW_REQUIRED


async def test_no_qr_is_manual_review(make_ctx):
    v = await run_doc(make_ctx, AadhaarQrResult(message="No QR code found"))
    assert v.status == DocStatus.MANUAL_REVIEW_REQUIRED and not v.passed("qr_detected")


def test_verhoeff():
    assert aadhaar.verhoeff_valid("234123412346")      # standard Verhoeff test vector extended
    assert not aadhaar.verhoeff_valid("234123412347")
    assert not aadhaar.verhoeff_valid("1234")


async def test_qr_second_upload_recomputes_verification(make_ctx):
    v = await run_doc(make_ctx, AadhaarQrResult(message="No QR code found"))
    assert v.status == DocStatus.MANUAL_REVIEW_REQUIRED
    aadhaar.reset_qr(v)
    aadhaar.apply_qr(v, qr_result(QrSignatureStatus.VERIFIED))
    engine.decide(v)
    assert v.status == DocStatus.VALID
