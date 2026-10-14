import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.verification import DocumentType, ExtractedFields, FieldValidation  # noqa: E402
from services.kyc.documents.base import DocContext  # noqa: E402
from services.kyc.providers import registry  # noqa: E402
from services.kyc.quality import assess_quality  # noqa: E402
from services.kyc.tampering import analyse_tampering  # noqa: E402

PROVIDER_ENV = [f"{p}_{s}" for p in ("PAN", "PASSPORT", "DL", "CITIZENSHIP", "EDUCATION")
                for s in ("API_URL", "API_KEY", "PROVIDER", "API_RETRIES", "API_TIMEOUT_S")]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in PROVIDER_ENV + ["APP_ENV", "AADHAAR_CERTIFICATE_PATH", "FACE_SIMILARITY_THRESHOLD",
                                "FACE_NO_MATCH_THRESHOLD", "TAMPER_SUSPICIOUS_THRESHOLD"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PAN_API_RETRIES", "0")
    registry._test_transports.clear()
    yield
    registry._test_transports.clear()


def textured_image(h=700, w=1000, seed=7) -> np.ndarray:
    """A sharp, evenly textured stand-in for a document photo (passes the quality gate)."""
    rng = np.random.default_rng(seed)
    base = rng.integers(90, 170, (h, w, 1)).astype(np.float32)
    noise = rng.normal(0, 18, (h, w, 3)).astype(np.float32)
    return np.clip(base + noise, 0, 255).astype(np.uint8)


@pytest.fixture
def make_ctx():
    def _make(doc_type, lines, *, face=True, img=None, fields=None, qr=None):
        from services.ocr_service import parse_extracted_fields
        full = " ".join(lines)
        detected, parsed = parse_extracted_fields(lines, full)
        image = img if img is not None else textured_image()
        return DocContext(
            doc_type=doc_type if doc_type is not None else detected, img=image, lines=lines, full_text=full,
            fields=fields or parsed, validation=FieldValidation(), quality=assess_quality(image),
            tamper=analyse_tampering(image, None, source_is_jpeg=False), face_extracted=face, aadhaar_qr=qr,
        )
    return _make
