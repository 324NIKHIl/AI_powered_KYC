from datetime import date, timedelta

import pytest

from models.verification import DocumentType
from services.kyc.documents import passport
from services.kyc.documents.mrz import check_digit, parse_td3, parse_mrz_from_ocr
from services.kyc.document_verification import verify_document
from services.kyc.result import DocStatus


def make_td3(surname="SHARMA", given="RAHUL KUMAR", number="J1234567", nat="IND", dob="900815", sex="M",
             expiry="300814", country="IND"):
    names = f"{surname}<<{given.replace(' ', '<')}"
    line1 = ("P<" + country + names).ljust(44, "<")
    n = number.ljust(9, "<")
    body = n + str(check_digit(n)) + nat + dob + str(check_digit(dob)) + sex + expiry + str(check_digit(expiry))
    personal = "<" * 14
    body += personal + "0"
    composite = body[0:10] + body[13:20] + body[21:43]
    return line1, body + str(check_digit(composite))


def viz_lines(**kw):
    return ["REPUBLIC OF INDIA", "PASSPORT", "Surname", kw.get("surname", "SHARMA"), "Given Name(s)",
            kw.get("given", "RAHUL KUMAR"), "Nationality INDIAN", "Date of Birth " + kw.get("dob", "15/08/1990"),
            "Date of Expiry " + kw.get("exp", "14/08/2030"), "Passport No. " + kw.get("num", "J1234567")]


def test_check_digit_icao_example():
    # ICAO 9303 specimen: document number L898902C3 → check digit 6, DOB 740812 → 2, expiry 120415 → 9
    assert check_digit("L898902C3") == 6
    assert check_digit("740812") == 2
    assert check_digit("120415") == 9


def test_valid_mrz_parses_and_checksums():
    r = parse_td3(*make_td3())
    assert r.structure_ok and r.checksums_ok
    assert (r.surname, r.given_names, r.passport_number, r.nationality) == ("SHARMA", "RAHUL KUMAR", "J1234567", "IND")
    assert r.dob == date(1990, 8, 15) and r.expiry == date(2030, 8, 14)


def test_tampered_mrz_fails_checksum():
    l1, l2 = make_td3()
    bad = l2[:14] + "1" + l2[15:]          # change a DOB digit
    r = parse_td3(l1, bad)
    assert r.structure_ok and not r.checksums_ok


def test_ocr_letter_for_digit_is_corrected():
    l1, l2 = make_td3()
    garbled = l2[:13] + "9O0815" + l2[19:]  # '9' '0' → 'O' in DOB (OCR confusion)
    r = parse_td3(l1, garbled)
    assert r.checksums_ok and r.ocr_corrected


def test_short_mrz_is_unreadable_not_invalid():
    l1, l2 = make_td3()
    r = parse_td3(l1, l2[:30])
    assert not r.structure_ok


async def run(ctx):
    return await verify_document(
        doc_type=ctx.doc_type, img=ctx.img, lines=ctx.lines, full_text=ctx.full_text, fields=ctx.fields,
        validation=ctx.validation, face_extracted=True)


async def test_passport_without_provider_is_unavailable_never_valid(make_ctx):
    ctx = make_ctx(DocumentType.PASSPORT, viz_lines() + list(make_td3()))
    v = await run(ctx)
    assert v.status == DocStatus.VERIFICATION_UNAVAILABLE
    assert v.passed("mrz_checksums") and v.passed("ocr_vs_mrz")
    assert v.external_verification is None
    assert v.evidence_level.value == "document_analysis"


async def test_expired_passport_invalid(make_ctx):
    expired = date.today() - timedelta(days=400)
    ctx = make_ctx(DocumentType.PASSPORT,
                   viz_lines(exp=expired.strftime("%d/%m/%Y")) + list(make_td3(expiry=expired.strftime("%y%m%d"))))
    v = await run(ctx)
    assert v.status == DocStatus.INVALID
    assert any(c.id == "passport_expiry" and c.outcome.value == "fail" for c in v.checks)


async def test_invalid_mrz_checksum_invalid(make_ctx):
    l1, l2 = make_td3()
    ctx = make_ctx(DocumentType.PASSPORT, viz_lines() + [l1, l2[:14] + "1" + l2[15:]])
    v = await run(ctx)
    assert v.status in (DocStatus.INVALID, DocStatus.SUSPICIOUS)
    assert not v.passed("mrz_checksums")


async def test_ocr_mrz_mismatch_is_suspicious(make_ctx):
    # Printed DOB / number differ from the MRZ → edited visual zone
    ctx = make_ctx(DocumentType.PASSPORT, viz_lines(dob="01/01/1985", num="K7654321") + list(make_td3()))
    v = await run(ctx)
    assert v.identity_consistent is False
    assert v.status == DocStatus.SUSPICIOUS


async def test_no_mrz_is_manual_review(make_ctx):
    ctx = make_ctx(DocumentType.PASSPORT, viz_lines())
    v = await run(ctx)
    assert v.status in (DocStatus.MANUAL_REVIEW_REQUIRED, DocStatus.VERIFICATION_UNAVAILABLE)
    assert v.status != DocStatus.VALID


def test_find_mrz_survives_ocr_noise():
    l1, l2 = make_td3()
    noisy1 = l1.replace("<", "«", 3)
    r = parse_mrz_from_ocr(["Header", noisy1 + " ", l2])
    assert r.found and r.structure_ok and r.checksums_ok
