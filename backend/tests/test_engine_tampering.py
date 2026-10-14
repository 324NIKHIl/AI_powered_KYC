import cv2
import numpy as np
from PIL import Image
import io

from services.kyc import engine
from services.kyc.result import CheckOutcome, DocStatus, DocumentVerification, mask_identifier
from services.kyc.tampering import analyse_tampering
from tests.conftest import textured_image


def doc(**kw):
    v = DocumentVerification(document_type="PAN", document_detected=True, ocr_success=True, format_valid=True)
    v.add("pan_format", "PAN format valid", CheckOutcome.PASS)
    for k, val in kw.items():
        setattr(v, k, val)
    return v


def test_ocr_and_format_alone_never_valid():
    v = engine.decide(doc())
    assert v.status != DocStatus.VALID and v.evidence_level.value == "document_analysis"


def test_authoritative_external_without_required_check_not_valid():
    v = DocumentVerification(document_type="PASSPORT", document_detected=True, ocr_success=True,
                             external_verification=True)
    assert engine.decide(v).status != DocStatus.VALID      # MRZ check digits (required) never passed


def test_external_unavailable_flag_gives_unavailable():
    assert engine.decide(doc(authority_unavailable=True)).status == DocStatus.VERIFICATION_UNAVAILABLE


def test_mock_external_never_valid():
    v = doc(external_verification=True)
    v.external.mock = True
    assert engine.decide(v).status != DocStatus.VALID


def test_failed_check_is_invalid_and_tamper_is_suspicious():
    v = doc()
    v.add("x", "bad", CheckOutcome.FAIL)
    assert engine.decide(v).status == DocStatus.INVALID
    assert engine.decide(doc(tampering_score=0.95)).status == DocStatus.SUSPICIOUS


def test_unreadable_is_manual_review():
    assert engine.decide(doc(unreadable=True)).status == DocStatus.MANUAL_REVIEW_REQUIRED


def test_risk_score_bounds_and_ordering():
    clean = engine.decide(doc()).risk_score
    bad = engine.decide(doc(cryptographic_verification=False)).risk_score
    assert 0 <= clean < bad <= 1


def test_mask_identifier():
    assert mask_identifier("ABCPK1234F") == "XXXXXX234F"
    assert mask_identifier("ABCPK1234F").endswith("234F") and "ABC" not in mask_identifier("ABCPK1234F")
    assert mask_identifier(None) is None


# ── Tampering heuristics ──────────────────────────────────────────────────────

def test_clean_image_has_low_tamper_score():
    assert analyse_tampering(textured_image(), None, source_is_jpeg=False).score < 0.35


def test_editing_software_metadata_is_flagged():
    buf = io.BytesIO()
    im = Image.fromarray(cv2.cvtColor(textured_image(300, 400), cv2.COLOR_BGR2RGB))
    exif = Image.Exif()
    exif[305] = "Adobe Photoshop 25.0"
    im.save(buf, "JPEG", exif=exif)
    r = analyse_tampering(textured_image(300, 400), buf.getvalue())
    assert r.score >= 0.4 and any("editing software" in i for i in r.indicators)


def test_pasted_region_with_different_noise_is_detected():
    img = textured_image(700, 1000).astype(np.float32)
    rng = np.random.default_rng(3)
    img[250:420, 300:620] = 140 + rng.normal(0, 2, (170, 320, 3))       # a smooth pasted/edited patch
    r = analyse_tampering(np.clip(img, 0, 255).astype(np.uint8), None, source_is_jpeg=False)
    assert r.score > 0.3 and r.indicators
