"""
Aadhaar verification: strongest local mechanism = UIDAI Secure QR signature.

The five facts are kept distinct (a QR existing proves nothing):
  QR detected → QR decoded → signature valid → certificate trusted → data consistent
Decoding / RSA verification itself lives in services/aadhaar_qr_service.py.
"""

from __future__ import annotations

import re
from typing import Optional

from models.verification import AadhaarQrResult, QrSignatureStatus
from services.kyc.documents.base import DocContext, start
from services.kyc.result import Check, CheckOutcome, DocumentVerification, mask_identifier

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(number: str) -> bool:
    """Aadhaar numbers carry a Verhoeff check digit — a structural (not authenticity) check."""
    if not re.fullmatch(r"\d{12}", number or ""):
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verify(ctx: DocContext) -> DocumentVerification:
    v = start(ctx, "AADHAAR", "Aadhaar card")
    digits = re.sub(r"\D", "", ctx.fields.id_number or "")

    # Layer: number structure (necessary, never sufficient)
    if len(digits) == 12 and digits[0] in "23456789":
        if verhoeff_valid(digits):
            v.format_valid = True
            v.add("aadhaar_format", "Aadhaar number format and checksum valid", CheckOutcome.PASS,
                  "Structural check only — it does not prove the number was issued")
        else:
            v.format_valid = False
            v.add("aadhaar_format", "Aadhaar number checksum", CheckOutcome.WARN,
                  "Checksum does not validate — either an OCR misread or an invalid number")
    elif digits:
        v.format_valid = False
        v.add("aadhaar_format", "Aadhaar number format", CheckOutcome.WARN, "Number is not a valid 12-digit Aadhaar number")
    else:
        v.add("aadhaar_format", "Aadhaar number", CheckOutcome.WARN, "Aadhaar number could not be read from the card")
    v.extracted = {
        "name": ctx.fields.name, "dob": ctx.fields.dob, "gender": ctx.fields.gender,
        "id_number": mask_identifier(digits),
    }

    apply_qr(v, ctx.aadhaar_qr)
    return v


def reset_qr(v: DocumentVerification) -> None:
    """Drop every QR-derived result so apply_qr() can be re-run (e.g. after the back-of-card upload)."""
    v.checks = [c for c in v.checks if not c.id.startswith("qr_") and c.id != "doc_supported"]
    v.cryptographic_verification = None
    v.identity_consistent = None
    v.authority_unavailable = False
    if v.document_type != "AADHAAR":   # a decoded Aadhaar QR identifies the document
        v.document_type = "AADHAAR"
        v.document_detected = True
        v.checks = [c for c in v.checks if c.id != "document_detected"]
        v.checks.insert(0, Check(id="document_detected", label="Aadhaar card detected", outcome=CheckOutcome.PASS))


def apply_qr(v: DocumentVerification, qr: Optional[AadhaarQrResult]) -> None:
    if qr is None or not qr.found:
        detected = bool(qr and "found, but" in (qr.message or ""))
        v.add("qr_detected", "QR code detected", CheckOutcome.PASS if detected else CheckOutcome.WARN,
              "" if detected else "No Aadhaar QR code found — upload the side of the card that has the QR code")
        v.add("qr_decoded", "QR decoded as Aadhaar Secure QR", CheckOutcome.SKIP,
              (qr.message if qr else "") or "No QR data to decode")
        v.add("qr_signature", "UIDAI digital signature", CheckOutcome.SKIP, "No signed data available to verify")
        v.add("qr_consistent", "Card data matches signed QR data", CheckOutcome.SKIP)
        return

    v.add("qr_detected", "QR code detected", CheckOutcome.PASS)
    v.add("qr_decoded", "QR decoded as Aadhaar Secure QR", CheckOutcome.PASS, f"format: {qr.qr_format}")

    status: Optional[QrSignatureStatus] = qr.signature_status
    if status == QrSignatureStatus.VERIFIED:
        v.cryptographic_verification = True
        v.add("qr_signature", "UIDAI digital signature valid", CheckOutcome.PASS,
              "RSA-SHA256 signature verified — the signed data has not been modified")
        v.add("qr_certificate", "Signing certificate trusted", CheckOutcome.PASS,
              "Verified against a configured UIDAI certificate")
    elif status == QrSignatureStatus.INVALID:
        v.cryptographic_verification = False
        v.add("qr_signature", "UIDAI digital signature", CheckOutcome.FAIL,
              "Signature is INVALID — the QR was not issued by UIDAI or its data was modified")
        v.add("qr_certificate", "Signing certificate trusted", CheckOutcome.FAIL,
              "No configured UIDAI certificate verifies this QR")
    elif status == QrSignatureStatus.UNSIGNED:
        v.add("qr_signature", "UIDAI digital signature", CheckOutcome.WARN,
              "Pre-2019 QR format carries no signature — authenticity cannot be proven from it")
        v.add("qr_certificate", "Signing certificate trusted", CheckOutcome.SKIP)
    else:  # UNVERIFIED — no UIDAI certificate configured
        v.authority_unavailable = True
        v.add("qr_signature", "UIDAI digital signature", CheckOutcome.WARN,
              "Signature NOT checked — no UIDAI certificate is configured on the server")
        v.add("qr_certificate", "Signing certificate trusted", CheckOutcome.WARN,
              "Set UIDAI_CERT_DIR or AADHAAR_CERTIFICATE_PATH to UIDAI's production certificate")

    checks = qr.field_checks or {}
    mismatches = [f for f, r in checks.items() if r == "mismatch"]
    matches = [f for f, r in checks.items() if r == "match"]
    if mismatches:
        v.identity_consistent = False
        v.add("qr_consistent", "Card data matches signed QR data", CheckOutcome.FAIL,
              "Printed card differs from the QR in: " + ", ".join(mismatches))
    elif matches:
        v.identity_consistent = True
        v.add("qr_consistent", "Card data matches signed QR data", CheckOutcome.PASS, "Matched: " + ", ".join(matches))
    else:
        v.add("qr_consistent", "Card data matches signed QR data", CheckOutcome.WARN,
              "OCR could not read enough of the card to compare with the QR")