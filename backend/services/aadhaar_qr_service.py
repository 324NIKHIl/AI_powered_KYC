"""
Aadhaar Secure QR verification.

Every Aadhaar card / e-Aadhaar issued since 2019 carries a "Secure QR" code: a
long decimal number encoding GZIP-compressed data that UIDAI signs with
RSA-2048 / SHA-256. It holds the holder's name, DOB, gender, partial address,
the last 4 digits of the Aadhaar number and the enrolment photo (JPEG 2000).

Decoding it lets us:
  1. verify UIDAI's signature offline (a forged or edited QR fails),
  2. compare the signed data against what OCR read from the printed card,
  3. compare the printed photo against the signed photo (photo substitution,
     the most common Aadhaar forgery) — done in verification_service.

Decompressed byte layout (text fields separated by 0xFF):
  [version "V2"], email/mobile indicator, reference id, name, dob, gender,
  care of, district, landmark, house, location, pincode, post office, state,
  street, sub district, VTC, [V2: last 4 digits of mobile],
  photo (JPEG 2000), [SHA-256 email / mobile hashes], signature (last 256 bytes)

The UIDAI public-key certificate(s) must be placed in UIDAI_CERT_DIR
(default: backend/certs/uidai/) — see the README there.
"""

from __future__ import annotations

import difflib
import glob
import io
import logging
import os
import re
import ssl
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from typing import Any, Iterator, Optional

import cv2
import numpy as np
from PIL import Image

from models.verification import (
    AadhaarQrResult,
    ExtractedFields,
    FieldValidation,
    QrSignatureStatus,
)
from utils.image_processing import save_image

logger = logging.getLogger(__name__)

UIDAI_CERT_DIR = os.getenv("UIDAI_CERT_DIR", os.path.join("certs", "uidai"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

SIGNATURE_LENGTH = 256
HASH_LENGTH = 32
NAME_MATCH_RATIO = 0.80
QR_PHOTO_MIN_SIDE = 240  # the embedded photo is tiny; upscale for display and face detection

# JPEG 2000 file (JP2 signature box) and raw codestream (SOC + SIZ markers)
_JP2_SIGNATURES = (b"\x00\x00\x00\x0cjP  \r\n\x87\n", b"\xff\x4f\xff\x51")

_V1_FIELDS = [
    "email_mobile_indicator", "reference_id", "name", "dob", "gender", "care_of",
    "district", "landmark", "house", "location", "pincode", "post_office",
    "state", "street", "sub_district", "vtc",
]
_V2_FIELDS = ["version", *_V1_FIELDS, "mobile_last4"]


@dataclass
class SecureQrPayload:
    qr_format: str
    fields: dict[str, str]
    photo: Optional[bytes]
    signed_data: bytes
    signature: bytes


# ── QR detection ──────────────────────────────────────────────────────────────

def _qr_variants(img: np.ndarray) -> Iterator[np.ndarray]:
    """Preprocessing variants, cheapest first — Secure QR codes are very dense."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    yield gray
    longest = max(gray.shape[:2])
    if longest > 2500:
        scale = 2000 / longest
        yield cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    elif longest < 1200:
        yield cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    yield cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    blurred = cv2.GaussianBlur(gray, (0, 0), 3)
    yield cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)  # unsharp mask


def _rectified_variants(gray: np.ndarray, detectors: list) -> Iterator[np.ndarray]:
    """
    Locate the QR, warp it flat onto a large square with a white quiet zone and
    yield cleaned-up versions. A Secure QR is ~150 modules wide, so in a normal
    phone photo each module is only 2–3 px and slightly skewed — too little for
    the decoder, although the detector can still find the corners.
    """
    corners = None
    for detector in detectors:
        try:
            ok, points = detector.detect(gray)
        except cv2.error:
            continue
        if ok and points is not None:
            corners = points.reshape(-1, 2)[:4].astype(np.float32)
            break
    if corners is None:
        return

    for size in (1200, 1500, 1800):
        margin = size // 10
        target = np.float32([[margin, margin], [margin + size, margin],
                             [margin + size, margin + size], [margin, margin + size]])
        matrix = cv2.getPerspectiveTransform(corners, target)
        flat = cv2.warpPerspective(gray, matrix, (size + 2 * margin, size + 2 * margin),
                                   flags=cv2.INTER_CUBIC, borderValue=255)
        yield flat
        yield cv2.adaptiveThreshold(flat, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, (size // 40) | 1, 5)
        yield cv2.addWeighted(flat, 1.8, cv2.GaussianBlur(flat, (0, 0), size / 300), -0.8, 0)


def _try_decode(variants: Iterator[np.ndarray], detectors: list) -> Optional[str]:
    for variant in variants:
        for detector in detectors:
            try:
                text, _, _ = detector.detectAndDecode(variant)
            except cv2.error:
                continue
            if text:
                return text
    return None


def decode_qr_strings(img: np.ndarray) -> list[str]:
    """Return every QR payload that can be decoded from the image."""
    detectors = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    detectors.append(cv2.QRCodeDetector())

    text = _try_decode(_qr_variants(img), detectors)
    if not text:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        text = _try_decode(_rectified_variants(gray, detectors), detectors)
    if text:
        return [text]

    # pyzbar copes better with very dense codes, if installed (needs the zbar system library)
    try:
        from pyzbar import pyzbar
    except ImportError:
        return []
    for variant in _qr_variants(img):
        decoded = [d.data.decode("iso-8859-1") for d in pyzbar.decode(variant) if d.type == "QRCODE"]
        if decoded:
            return decoded
    return []


# ── Secure QR parsing ─────────────────────────────────────────────────────────

def _decimal_to_bytes(digits: str) -> bytes:
    # Chunked: Python refuses int() on strings above 4300 digits, and Secure QRs can exceed that
    value = 0
    for i in range(0, len(digits), 1000):
        chunk = digits[i:i + 1000]
        value = value * 10 ** len(chunk) + int(chunk)
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def _decompress(raw: bytes) -> bytes:
    for wbits in (16 + zlib.MAX_WBITS, zlib.MAX_WBITS, -zlib.MAX_WBITS):  # gzip, zlib, raw deflate
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    raise ValueError("QR payload is not compressed Aadhaar data")


def _find_photo_start(data: bytes, field_count: int) -> int:
    """
    Offset where the JPEG 2000 photo begins. The photo contains 0xFF bytes itself,
    so text fields can't simply be split on the delimiter. Per spec the photo follows
    the last text field; searching for the JPEG 2000 signature from there also copes
    with newer QR versions that append extra text fields.
    """
    pos = -1
    for _ in range(field_count):
        pos = data.index(b"\xff", pos + 1)
    after_fields = pos + 1
    found = [i for i in (data.find(sig, after_fields) for sig in _JP2_SIGNATURES) if i >= 0]
    return min(found) if found else after_fields


def parse_secure_qr(qr_text: str) -> SecureQrPayload:
    digits = qr_text.strip()
    if not digits.isdigit() or len(digits) < 200:
        raise ValueError("not an Aadhaar Secure QR")

    data = _decompress(_decimal_to_bytes(digits))
    if len(data) <= SIGNATURE_LENGTH or b"\xff" not in data:
        raise ValueError("QR payload too short")
    signed_data, signature = data[:-SIGNATURE_LENGTH], data[-SIGNATURE_LENGTH:]

    version = signed_data[:signed_data.index(b"\xff")]
    versioned = re.fullmatch(rb"V\d+", version) is not None
    names = _V2_FIELDS if versioned else _V1_FIELDS

    photo_start = _find_photo_start(signed_data, len(names))
    values = signed_data[:photo_start].split(b"\xff")
    fields = {name: values[i].decode("iso-8859-1").strip() for i, name in enumerate(names) if i < len(values)}

    hashes = {"1": 1, "2": 1, "3": 2}.get(fields.get("email_mobile_indicator", "0"), 0)
    photo = signed_data[photo_start:len(signed_data) - hashes * HASH_LENGTH] or None

    qr_format = f"secure_{version.decode().lower()}" if versioned else "secure_v1"
    return SecureQrPayload(qr_format, fields, photo, signed_data, signature)


def _der_element(der: bytes, pos: int) -> tuple[int, int, int]:
    """Parse one DER TLV at pos → (tag, content_start, end)."""
    tag, length = der[pos], der[pos + 1]
    pos += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(der[pos:pos + n], "big")
        pos += n
    return tag, pos, pos + length


def _public_key_from_certificate_der(der: bytes):
    """
    Extract SubjectPublicKeyInfo from a certificate without full X.509 parsing.
    Some UIDAI certificates contain DER encoding quirks (e.g. an explicitly
    encoded default "critical=FALSE") that cryptography >= 42 rejects outright.
    """
    from cryptography.hazmat.primitives.serialization import load_der_public_key

    _, cert_start, _ = _der_element(der, 0)         # Certificate
    _, pos, _ = _der_element(der, cert_start)       # tbsCertificate
    tag, _, end = _der_element(der, pos)
    if tag == 0xA0:                                 # optional [0] version
        pos = end
    for _ in range(5):                              # serial, signature alg, issuer, validity, subject
        pos = _der_element(der, pos)[2]
    return load_der_public_key(der[pos:_der_element(der, pos)[2]])


def _read_certificate(blob: bytes) -> tuple[Any, str]:
    """Return (public_key, subject) for a PEM or DER certificate."""
    from cryptography import x509

    is_pem = b"-----BEGIN" in blob
    try:
        cert = x509.load_pem_x509_certificate(blob) if is_pem else x509.load_der_x509_certificate(blob)
        return cert.public_key(), cert.subject.rfc4514_string()
    except ValueError:
        der = ssl.PEM_cert_to_DER_cert(blob.decode("ascii")) if is_pem else blob
        # Subject strings are plain ASCII inside the DER, good enough for the staging check
        subject = "staging" if b"staging" in der.lower() else "(unparsed)"
        return _public_key_from_certificate_der(der), subject


def is_staging_certificate(subject: str) -> bool:
    return any(word in subject.lower() for word in ("staging", "preprod", "pre-prod", "pre-production"))


def _load_uidai_keys() -> list[tuple[str, Any]]:
    keys = []
    for path in sorted(glob.glob(os.path.join(UIDAI_CERT_DIR, "*"))):
        if not path.lower().endswith((".cer", ".crt", ".pem", ".der")):
            continue
        with open(path, "rb") as fh:
            blob = fh.read()
        try:
            public_key, subject = _read_certificate(blob)
        except Exception as exc:
            logger.warning("Skipping unreadable certificate %s: %s", path, exc)
            continue
        if is_staging_certificate(subject):
            # Real cards are signed with UIDAI's production key; a staging cert can only
            # ever report "invalid", which would falsely flag genuine cards as tampered.
            logger.warning(
                "Skipping %s: staging/test certificate (%s) — it cannot verify real Aadhaar QR codes. "
                "Add UIDAI's production Secure QR certificate.",
                path, subject,
            )
            continue
        keys.append((os.path.basename(path), public_key))
    return keys


def verify_signature(payload: SecureQrPayload) -> tuple[QrSignatureStatus, Optional[str]]:
    """Check the RSA-SHA256 signature against every configured UIDAI certificate."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    keys = _load_uidai_keys()
    if not keys:
        logger.warning("No UIDAI certificates in %s — QR signature not checked", UIDAI_CERT_DIR)
        return QrSignatureStatus.UNVERIFIED, None

    for name, key in keys:
        try:
            key.verify(payload.signature, payload.signed_data, padding.PKCS1v15(), hashes.SHA256())
            return QrSignatureStatus.VERIFIED, name
        except (InvalidSignature, TypeError, ValueError, AttributeError):
            continue  # wrong key (UIDAI has rotated keys over the years) or non-RSA cert
    return QrSignatureStatus.INVALID, None


def parse_legacy_xml_qr(qr_text: str) -> dict[str, Optional[str]]:
    """Pre-2019 Aadhaar QR: plain, unsigned XML attributes."""
    root = ET.fromstring(qr_text.strip().encode("utf-8"))
    attrs = root.attrib
    uid = re.sub(r"\D", "", attrs.get("uid", ""))
    return {
        "name": attrs.get("name"),
        "dob": attrs.get("dob") or attrs.get("yob"),
        "gender": attrs.get("gender"),
        "aadhaar_last4": uid[-4:] or None,
        "district": attrs.get("dist"),
        "state": attrs.get("state"),
        "pincode": attrs.get("pc"),
    }


# ── Cross-checks against OCR ──────────────────────────────────────────────────

def _normalise_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z]", " ", name.lower()).split())


def _names_match(a: str, b: str) -> bool:
    a, b = _normalise_name(a), _normalise_name(b)
    if sorted(a.split()) == sorted(b.split()):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= NAME_MATCH_RATIO


def _dob_parts(dob: str) -> list[int]:
    return [int(p) for p in re.findall(r"\d+", dob)]


def _dobs_match(qr_dob: str, ocr_dob: str) -> bool:
    qr, ocr = _dob_parts(qr_dob), _dob_parts(ocr_dob)
    if len(qr) == 1:  # legacy QR may only carry the year of birth
        return bool(ocr) and qr[0] == max(ocr)
    return qr == ocr


_FLAG_TEXT = {
    "name": "Name on the card differs from the signed QR data",
    "dob": "Date of birth on the card differs from the signed QR data",
    "gender": "Gender on the card differs from the signed QR data",
    "aadhaar_last4": "Aadhaar number on the card differs from the signed QR data",
}


def cross_check(
    qr_fields: dict[str, Optional[str]],
    ocr: ExtractedFields,
    validation: FieldValidation,
) -> tuple[dict[str, str], list[str]]:
    """
    Compare signed QR data with OCR output. OCR values are only compared when
    OCR itself validated them, so OCR misreads don't show up as tampering.
    """
    ocr_digits = re.sub(r"\D", "", ocr.id_number or "")
    comparisons = {
        "name": (qr_fields.get("name"), ocr.name if validation.name else None, _names_match),
        "dob": (qr_fields.get("dob"), ocr.dob if validation.dob else None, _dobs_match),
        "gender": (
            qr_fields.get("gender"),
            ocr.gender,
            lambda q, o: q.strip()[:1].upper() == o.strip()[:1].upper(),
        ),
        "aadhaar_last4": (
            qr_fields.get("aadhaar_last4"),
            ocr_digits[-4:] if validation.id_number and ocr_digits else None,
            lambda q, o: q == o,
        ),
    }

    checks: dict[str, str] = {}
    flags: list[str] = []
    for field, (qr_value, ocr_value, same) in comparisons.items():
        if not qr_value or not ocr_value:
            checks[field] = "unavailable"
        elif same(qr_value, ocr_value):
            checks[field] = "match"
        else:
            checks[field] = "mismatch"
            flags.append(_FLAG_TEXT[field])
    return checks, flags


# ── Photo ─────────────────────────────────────────────────────────────────────

def _decode_photo(photo: bytes) -> Optional[np.ndarray]:
    try:
        pil = Image.open(io.BytesIO(photo))
        pil.load()
        img = cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception:
        img = cv2.imdecode(np.frombuffer(photo, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    # The QR photo is cropped tight to the face; face detectors need some margin around it
    pad = max(img.shape[:2]) // 4
    fill = [int(c) for c in img.reshape(-1, 3).mean(axis=0)]
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=fill)
    shortest = min(img.shape[:2])
    if shortest < QR_PHOTO_MIN_SIDE:
        scale = QR_PHOTO_MIN_SIDE / shortest
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return img


# ── Orchestration ─────────────────────────────────────────────────────────────

def _message(status: Optional[QrSignatureStatus], flags: list[str]) -> str:
    if status == QrSignatureStatus.INVALID:
        return "QR signature is invalid — this QR code was not issued by UIDAI or was edited"
    if flags:
        return "Aadhaar QR decoded, but the printed card does not match it"
    if status == QrSignatureStatus.VERIFIED:
        return "Aadhaar QR signature verified with UIDAI's certificate — card details match"
    if status == QrSignatureStatus.UNSIGNED:
        return "Old-format Aadhaar QR (pre-2019) — it carries no digital signature"
    return "Aadhaar QR decoded, but its signature was not checked (no UIDAI certificate configured)"


def _process_secure(
    qr_text: str,
    session_id: str,
    ocr: ExtractedFields,
    validation: FieldValidation,
) -> AadhaarQrResult:
    payload = parse_secure_qr(qr_text)
    status, certificate = verify_signature(payload)
    f = payload.fields
    fields = {
        "name": f.get("name"),
        "dob": f.get("dob"),
        "gender": f.get("gender"),
        "aadhaar_last4": (f.get("reference_id") or "")[:4] or None,
        "district": f.get("district"),
        "state": f.get("state"),
        "pincode": f.get("pincode"),
    }

    photo_path = None
    photo_img = _decode_photo(payload.photo) if payload.photo else None
    if photo_img is not None:
        photo_path = save_image(photo_img, os.path.join(UPLOAD_DIR, "faces"), prefix=f"qr_face_{session_id}")
    else:
        logger.warning("[%s] Aadhaar QR photo could not be decoded", session_id)

    checks, flags = cross_check(fields, ocr, validation)
    if status == QrSignatureStatus.INVALID:
        flags.insert(0, "UIDAI signature is invalid — QR code is forged or was edited")

    logger.info(
        "[%s] Aadhaar QR format=%s signature=%s cert=%s checks=%s photo=%s",
        session_id, payload.qr_format, status.value, certificate, checks, photo_path,
    )
    return AadhaarQrResult(
        found=True,
        qr_format=payload.qr_format,
        signature_status=status,
        signing_certificate=certificate,
        fields=fields,
        field_checks=checks,
        photo_path=photo_path,
        tamper_flags=flags,
        message=_message(status, flags),
    )


def process_aadhaar_qr(
    img: np.ndarray,
    session_id: str,
    ocr: ExtractedFields,
    validation: FieldValidation,
) -> AadhaarQrResult:
    """Find, decode, verify and cross-check an Aadhaar QR code in an image."""
    texts = decode_qr_strings(img)
    if not texts:
        logger.info("[%s] No QR code found in image shape=%s", session_id, img.shape)
        return AadhaarQrResult(message="No QR code found — upload the side of the card that has the QR code")

    for text in texts:
        stripped = text.strip()
        if stripped.isdigit():
            try:
                return _process_secure(stripped, session_id, ocr, validation)
            except ValueError as exc:
                logger.warning("[%s] Numeric QR is not a valid Aadhaar Secure QR: %s", session_id, exc)
        elif "PrintLetterBarcodeData" in stripped:
            try:
                fields = parse_legacy_xml_qr(stripped)
            except ET.ParseError as exc:
                logger.warning("[%s] Legacy Aadhaar QR XML unreadable: %s", session_id, exc)
                continue
            checks, flags = cross_check(fields, ocr, validation)
            logger.info("[%s] Legacy Aadhaar QR checks=%s", session_id, checks)
            return AadhaarQrResult(
                found=True,
                qr_format="legacy_xml",
                signature_status=QrSignatureStatus.UNSIGNED,
                fields=fields,
                field_checks=checks,
                tamper_flags=flags,
                message=_message(QrSignatureStatus.UNSIGNED, flags),
            )

    return AadhaarQrResult(message="A QR code was found, but it is not an Aadhaar QR code")
