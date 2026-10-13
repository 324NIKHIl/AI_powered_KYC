"""
Passport verification: OCR + MRZ (ICAO 9303 TD3) + OCR-vs-MRZ comparison + document analysis,
then the external passport provider. MRZ check digits prove the MRZ is internally consistent —
they are public arithmetic, NOT proof that the passport was issued, so authenticity comes
only from the external layer.
"""

from __future__ import annotations

import re
from datetime import date

from services.kyc.documents.base import DocContext, start
from services.kyc.documents.mrz import ICAO_CODES, MrzResult, normalise_mrz_line, parse_mrz_from_ocr
from services.kyc.external import run_external_verification
from services.kyc.result import CheckOutcome, DocumentVerification, mask_identifier
from services.kyc.text_utils import find_dates, fuzzy_contains

_DEMONYMS = {
    "IND": ("INDIAN", "INDIA"), "NPL": ("NEPALI", "NEPALESE", "NEPAL"), "USA": ("UNITED STATES", "AMERICAN"),
    "GBR": ("BRITISH", "UNITED KINGDOM"), "CAN": ("CANADIAN", "CANADA"), "AUS": ("AUSTRALIAN", "AUSTRALIA"),
    "LKA": ("SRI LANKAN", "SRI LANKA"), "BGD": ("BANGLADESH",), "PAK": ("PAKISTAN",), "DEU": ("DEUTSCH", "GERMAN"),
    "FRA": ("FRANCAISE", "FRENCH", "FRANCE"), "SGP": ("SINGAPORE",),
}


def _viz_lines(ctx: DocContext, mrz: MrzResult) -> list[str]:
    """OCR lines of the visual inspection zone (everything that is not an MRZ line)."""
    mrz_norm = {normalise_mrz_line(l) for l in mrz.lines}
    out = []
    for line in ctx.lines:
        n = normalise_mrz_line(line)
        if n in mrz_norm or (len(n) >= 30 and n.count("<") >= 3):
            continue
        out.append(line)
    return out


def compare_ocr_with_mrz(ctx: DocContext, mrz: MrzResult) -> dict[str, str]:
    """field → match | mismatch | unavailable (OCR visual zone vs MRZ)."""
    viz = _viz_lines(ctx, mrz)
    viz_text = " ".join(viz).translate(str.maketrans("", "", ""))
    viz_upper = viz_text.upper()
    result: dict[str, str] = {}

    # passport number
    candidates = set(re.findall(r"\b[A-Z][0-9]{7}\b", viz_upper)) | set(re.findall(r"\b[A-Z0-9]{8,9}\b", viz_upper))
    candidates = {c for c in candidates if any(ch.isdigit() for ch in c)}
    if mrz.passport_number and fuzzy_contains(viz_upper, mrz.passport_number, ratio=0.95):
        result["passport_number"] = "match"
    elif candidates:
        result["passport_number"] = "mismatch"
    else:
        result["passport_number"] = "unavailable"

    dates = find_dates(viz_text)
    for key, value in (("date_of_birth", mrz.dob), ("expiry_date", mrz.expiry)):
        if value is None or not dates:
            result[key] = "unavailable"
        else:
            result[key] = "match" if value in dates else "mismatch"

    for key, value in (("surname", mrz.surname), ("given_names", mrz.given_names.split(" ")[0] if mrz.given_names else "")):
        if not value or not viz_upper.strip():
            result[key] = "unavailable"
        else:
            result[key] = "match" if fuzzy_contains(viz_upper, value, ratio=0.82) else "mismatch"

    hints = _DEMONYMS.get(mrz.nationality)
    if hints is None:
        result["nationality"] = "unavailable"
    else:
        result["nationality"] = "match" if any(h in viz_upper for h in hints) else "mismatch"
    return result


def verify_sync(ctx: DocContext) -> tuple[DocumentVerification, MrzResult]:
    v = start(ctx, "PASSPORT", "Passport")
    mrz = parse_mrz_from_ocr(ctx.lines)

    # ── MRZ layers ────────────────────────────────────────────────────────────
    if not mrz.found:
        v.add("mrz_detected", "MRZ detected", CheckOutcome.WARN, "No Machine Readable Zone could be read")
        v.add("mrz_checksums", "MRZ check digits", CheckOutcome.SKIP)
        return v, mrz
    v.add("mrz_detected", "MRZ detected", CheckOutcome.PASS)

    if not mrz.structure_ok:
        v.format_valid = None
        v.add("mrz_structure", "MRZ structure", CheckOutcome.WARN,
              mrz.problems[0] + " — it may have been misread; retake a sharper photo")
        v.add("mrz_checksums", "MRZ check digits", CheckOutcome.SKIP, "MRZ could not be read completely")
        return v, mrz
    v.add("mrz_structure", "MRZ structure valid (ICAO 9303 TD3)", CheckOutcome.PASS)

    v.format_valid = mrz.checksums_ok and mrz.dob is not None and mrz.expiry is not None
    if mrz.checksums_ok and not any("date" in p or "sex" in p for p in mrz.problems):
        v.add("mrz_checksums", "MRZ check digits valid", CheckOutcome.PASS,
              ("Corrected OCR letter/digit confusions in numeric fields. " if mrz.ocr_corrected else "")
              + "Check digits are public arithmetic — they do not prove the passport was issued")
    else:
        v.add("mrz_checksums", "MRZ check digits", CheckOutcome.FAIL, "; ".join(mrz.problems).capitalize())

    if mrz.nationality in ICAO_CODES and (not mrz.issuing_country or mrz.issuing_country in ICAO_CODES):
        v.add("mrz_country", "Issuing state and nationality codes valid", CheckOutcome.PASS)
    else:
        v.add("mrz_country", "Issuing state and nationality codes", CheckOutcome.WARN,
              "Country code is not a recognised ICAO code")

    # ── Expiry ────────────────────────────────────────────────────────────────
    if mrz.expiry is not None:
        if mrz.expiry < date.today():
            v.add("passport_expiry", "Passport not expired", CheckOutcome.FAIL, f"Passport expired on {mrz.expiry.isoformat()}")
        else:
            v.add("passport_expiry", "Passport not expired", CheckOutcome.PASS, f"Valid until {mrz.expiry.isoformat()}")

    # ── OCR vs MRZ ────────────────────────────────────────────────────────────
    cmp = compare_ocr_with_mrz(ctx, mrz)
    mism = [k.replace("_", " ") for k, r in cmp.items() if r == "mismatch"]
    matched = [k.replace("_", " ") for k, r in cmp.items() if r == "match"]
    if mism:
        v.identity_consistent = False
        v.add("ocr_vs_mrz", "Printed data matches the MRZ", CheckOutcome.FAIL,
              "Printed data differs from the MRZ in: " + ", ".join(mism))
    elif matched:
        v.identity_consistent = True
        v.add("ocr_vs_mrz", "Printed data matches the MRZ", CheckOutcome.PASS, "Matched: " + ", ".join(matched))
    else:
        v.add("ocr_vs_mrz", "Printed data matches the MRZ", CheckOutcome.WARN,
              "The printed fields could not be read well enough to compare with the MRZ")

    if not ctx.face_extracted:
        v.add("passport_photo", "Photo present", CheckOutcome.WARN, "No face found on the document")

    v.extracted = {
        "surname": mrz.surname, "given_names": mrz.given_names, "passport_number": mask_identifier(mrz.passport_number),
        "nationality": mrz.nationality, "issuing_country": mrz.issuing_country, "sex": mrz.sex,
        "dob": mrz.dob.isoformat() if mrz.dob else None, "expiry": mrz.expiry.isoformat() if mrz.expiry else None,
    }
    return v, mrz


async def verify(ctx: DocContext) -> DocumentVerification:
    v, mrz = verify_sync(ctx)
    if mrz.structure_ok and not v.failed():
        full_name = f"{mrz.given_names} {mrz.surname}".strip()
        dob = mrz.dob.strftime("%d/%m/%Y") if mrz.dob else None
        await run_external_verification(
            v, "PASSPORT",
            {"document_number": mrz.passport_number, "name": full_name, "surname": mrz.surname,
             "given_names": mrz.given_names, "dob": dob, "nationality": mrz.nationality, "sex": mrz.sex,
             "expiry": mrz.expiry.strftime("%d/%m/%Y") if mrz.expiry else None},
            label="Passport verified with external provider",
            expected_name=full_name, expected_dob=dob, document_text=ctx.full_text,
        )
    return v
