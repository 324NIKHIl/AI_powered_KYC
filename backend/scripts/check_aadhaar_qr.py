"""
Check an Aadhaar Secure QR from the command line — no server, MongoDB or face
models needed. Use it to confirm the QR can be read from your photo and that
the certificates in certs/uidai/ verify its signature.

Usage (run from backend/):
    python scripts/check_aadhaar_qr.py path/to/aadhaar_back.jpg
    python scripts/check_aadhaar_qr.py path/to/aadhaar_back.jpg --tamper   # demo: edited QR fails
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import cv2  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402

from services import aadhaar_qr_service as q  # noqa: E402


def _describe_certificates() -> None:
    print(f"Certificates in {os.path.abspath(q.UIDAI_CERT_DIR)}:")
    names = sorted(os.listdir(q.UIDAI_CERT_DIR)) if os.path.isdir(q.UIDAI_CERT_DIR) else []
    certs = [n for n in names if n.lower().endswith((".cer", ".crt", ".pem", ".der"))]
    if not certs:
        print("  (none) — signature will be reported as 'unverified'")
    for name in certs:
        with open(os.path.join(q.UIDAI_CERT_DIR, name), "rb") as fh:
            blob = fh.read()
        print(f"  {name}")
        try:
            cert = (x509.load_pem_x509_certificate(blob) if b"-----BEGIN" in blob
                    else x509.load_der_x509_certificate(blob))
            subject = cert.subject.rfc4514_string()
            # *_utc attributes exist from cryptography 42; older versions only have the naive ones
            start = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
            end = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
            print(f"      subject: {subject}")
            print(f"      valid:   {start:%Y-%m-%d} → {end:%Y-%m-%d}")
        except ValueError:
            try:
                _, subject = q._read_certificate(blob)
            except Exception as exc:
                print(f"      NOT a readable certificate: {exc}")
                continue
            print("      non-standard encoding — public key extracted directly")
        if q.is_staging_certificate(subject):
            print("      ⚠ STAGING certificate — skipped, it cannot verify real Aadhaar cards")
    print()


def _verifies(key, payload: q.SecureQrPayload, signed_data: bytes) -> bool:
    try:
        key.verify(payload.signature, signed_data, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, TypeError, ValueError, AttributeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode and verify an Aadhaar Secure QR image")
    parser.add_argument("image", help="photo / scan (JPG or PNG) showing the Aadhaar QR code")
    parser.add_argument("--tamper", action="store_true", help="also show that editing the QR data breaks the signature")
    args = parser.parse_args()

    _describe_certificates()

    img = cv2.imread(args.image)
    if img is None:
        print(f"Could not read image: {args.image} (use JPG/PNG — for a PDF, screenshot the page)")
        return 1
    print(f"Image: {args.image} {img.shape[1]}×{img.shape[0]}px")

    texts = q.decode_qr_strings(img)
    if not texts:
        print("\n✗ No QR code could be decoded. Tips:")
        print("  • photograph the QR close up so it fills most of the frame, in focus, no glare")
        print("  • crop the image to just the QR code and try again")
        print("  • pip install pyzbar (plus: brew install zbar) — it reads dense codes better")
        return 1

    text = texts[0].strip()
    if not text.isdigit():
        if "PrintLetterBarcodeData" in text:
            print("\n⚠ Old (pre-2019) Aadhaar QR — plain XML with no signature to verify:")
            for k, v in q.parse_legacy_xml_qr(text).items():
                print(f"  {k:14} {v}")
        else:
            print(f"\n✗ Decoded a QR code, but it is not an Aadhaar QR: {text[:80]!r}")
        return 1

    payload = q.parse_secure_qr(text)
    f = payload.fields
    print(f"\n✓ Aadhaar Secure QR decoded ({payload.qr_format}, {len(text)} digits)")
    for label, value in [
        ("name", f.get("name")), ("dob", f.get("dob")), ("gender", f.get("gender")),
        ("aadhaar_last4", (f.get("reference_id") or "")[:4]), ("district", f.get("district")),
        ("state", f.get("state")), ("pincode", f.get("pincode")),
    ]:
        print(f"  {label:14} {value}")

    if payload.photo:
        photo = q._decode_photo(payload.photo)
        if photo is not None:
            out = os.path.join(q.UPLOAD_DIR, "faces", "qr_check_photo.jpg")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            cv2.imwrite(out, photo)
            print(f"  photo          {len(payload.photo)} bytes → saved to {out}")
        else:
            print(f"  photo          {len(payload.photo)} bytes, could NOT be decoded (JPEG 2000 support missing in Pillow?)")

    print("\nSignature check:")
    keys = q._load_uidai_keys()
    for name, key in keys:
        print(f"  {name}: {'✓ VERIFIES this QR' if _verifies(key, payload, payload.signed_data) else '✗ does not verify'}")
    status, cert = q.verify_signature(payload)
    print(f"\nResult: signature {status.value.upper()}" + (f" (by {cert})" if cert else ""))
    if status.value == "invalid":
        print("  None of the certificates verify this QR. A staging / pre-production certificate from the\n"
              "  developer section will never verify a real card — use UIDAI's production Secure QR /\n"
              "  offline e-KYC certificate. If you have several, put them all in the folder.")

    if args.tamper and keys:
        name_bytes = (f.get("name") or "").encode("iso-8859-1")
        edited = payload.signed_data.replace(name_bytes, name_bytes[::-1], 1) if name_bytes else payload.signed_data[:-1] + b"\x00"
        still_valid = any(_verifies(key, payload, edited) for _, key in keys)
        print(f"\nTamper demo: name reversed inside the signed data → signature {'still valid?!' if still_valid else 'INVALID ✓'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
