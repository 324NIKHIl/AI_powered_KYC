"""
Driving licence verification (India-structured, extensible).
OCR → licence-number structure → issuing state → field sanity → external provider.
Regex validity is *not* authenticity; only the external layer can establish that.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from services.kyc.documents.base import DocContext, start
from services.kyc.external import run_external_verification
from services.kyc.result import CheckOutcome, DocumentVerification, mask_identifier
from services.kyc.text_utils import clean_alnum, find_dates, parse_date

# RTO state/UT codes used in Indian licence numbers
STATE_CODES = {
    "AN": "Andaman & Nicobar", "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar",
    "CG": "Chhattisgarh", "CH": "Chandigarh", "DD": "Daman & Diu", "DL": "Delhi", "DN": "Dadra & Nagar Haveli",
    "GA": "Goa", "GJ": "Gujarat", "HP": "Himachal Pradesh", "HR": "Haryana", "JH": "Jharkhand",
    "JK": "Jammu & Kashmir", "KA": "Karnataka", "KL": "Kerala", "LA": "Ladakh", "LD": "Lakshadweep",
    "MH": "Maharashtra", "ML": "Meghalaya", "MN": "Manipur", "MP": "Madhya Pradesh", "MZ": "Mizoram",
    "NL": "Nagaland", "OD": "Odisha", "OR": "Odisha", "PB": "Punjab", "PY": "Puducherry", "RJ": "Rajasthan",
    "SK": "Sikkim", "TN": "Tamil Nadu", "TR": "Tripura", "TS": "Telangana", "UK": "Uttarakhand",
    "UA": "Uttarakhand", "UP": "Uttar Pradesh", "WB": "West Bengal",
}
# SS RR YYYY NNNNNNN  (state, RTO, year, 7-digit serial); separators optional. Older cards: SS-RR/YY/NNNNN.
_DL_MODERN = re.compile(r"^([A-Z]{2})(\d{2})((?:19|20)\d{2})(\d{7})$")
_DL_LOOSE = re.compile(r"\b([A-Z]{2})[\s\-]?(\d{2})[\s\-]?((?:19|20)\d{2})[\s\-]?(\d{7})\b")
LAYOUT_MARKERS = ("DRIVING LICEN", "DRIVING LICENSE", "LICENCE TO DRIVE", "FORM OF LICENCE", "UNION OF INDIA",
                  "TRANSPORT", "VALID TILL", "VALIDITY", "COV", "DOI", "DOB")


def find_licence_number(text: str) -> Optional[str]:
    upper = text.upper()
    m = _DL_LOOSE.search(upper)
    if m:
        return "".join(m.groups())
    # OCR often merges everything; search the cleaned text too
    m = re.search(r"([A-Z]{2}\d{2}(?:19|20)\d{2}\d{7})", clean_alnum(upper))
    return m.group(1) if m else None


def validate_licence_number(number: Optional[str]) -> tuple[bool, str]:
    if not number:
        return False, "no licence number found"
    m = _DL_MODERN.fullmatch(clean_alnum(number))
    if not m:
        return False, "does not follow the SS RR YYYY NNNNNNN structure"
    state, _, year, _ = m.groups()
    if state not in STATE_CODES:
        return False, f"'{state}' is not a recognised state/UT code"
    if not (1950 <= int(year) <= date.today().year):
        return False, f"issue year {year} is not plausible"
    return True, STATE_CODES[state]


def _labelled_date(text: str, labels: tuple[str, ...]) -> Optional[date]:
    for label in labels:
        m = re.search(label + r"[^0-9A-Za-z]{0,6}(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", text, re.IGNORECASE)
        if m:
            d = parse_date(m.group(1))
            if d:
                return d
    return None


def verify_sync(ctx: DocContext) -> tuple[DocumentVerification, Optional[str]]:
    v = start(ctx, "DRIVING_LICENCE", "Driving licence")
    text = ctx.full_text
    number = find_licence_number(text)
    ok, info = validate_licence_number(number)

    if number is None:
        v.add("dl_format", "Licence number", CheckOutcome.WARN, "No licence number could be read")
        return v, None
    if not ok:
        v.format_valid = False
        v.add("dl_format", "Licence number format", CheckOutcome.FAIL, f"Licence number {info}")
        return v, None
    v.format_valid = True
    v.add("dl_format", "Licence number format valid", CheckOutcome.PASS,
          "Structure only — a well-formed number is not proof that the licence was issued")
    v.add("dl_state", "Issuing state identified", CheckOutcome.PASS, info)

    dob = _labelled_date(text, (r"\bD\.?O\.?B\b", r"DATE OF BIRTH")) or ctx.fields.dob and parse_date(ctx.fields.dob)
    issue = _labelled_date(text, (r"\bD\.?O\.?I\b", r"ISSUE DATE", r"DATE OF ISSUE", r"ISSUED"))
    valid_till = _labelled_date(text, (r"VALID\s*TILL", r"VALIDITY", r"\bNT\b", r"VALID UPTO"))
    if valid_till is None:
        dates = [d for d in find_dates(text) if d.year >= date.today().year - 1]
        valid_till = max(dates) if dates else None

    if valid_till is not None:
        if valid_till < date.today():
            v.add("dl_validity", "Licence not expired", CheckOutcome.FAIL, f"Licence validity ended on {valid_till.isoformat()}")
        else:
            v.add("dl_validity", "Licence not expired", CheckOutcome.PASS, f"Valid until {valid_till.isoformat()}")
    else:
        v.add("dl_validity", "Licence validity", CheckOutcome.WARN, "Validity date could not be read")

    if dob and issue:
        if (issue - dob).days / 365.25 < 16:
            v.add("dl_dates", "Dates consistent", CheckOutcome.FAIL, "Licence issued before the holder was 16")
        else:
            v.add("dl_dates", "Dates consistent", CheckOutcome.PASS)
    m = _DL_MODERN.fullmatch(clean_alnum(number))
    if m and dob and int(m.group(3)) - dob.year < 16:
        v.add("dl_year", "Licence-number year consistent with date of birth", CheckOutcome.FAIL,
              "The year in the licence number is earlier than the holder's 16th birthday")

    markers = sum(1 for k in LAYOUT_MARKERS[:5] if k in ctx.text_upper)
    v.add("dl_layout", "Document layout consistent with a driving licence",
          CheckOutcome.PASS if markers >= 1 else CheckOutcome.WARN,
          "" if markers >= 1 else "Expected driving-licence headings were not found")
    if not ctx.face_extracted:
        v.add("dl_photo", "Photo present", CheckOutcome.WARN, "No face found on the document")

    v.extracted = {"name": ctx.fields.name, "dob": dob.isoformat() if dob else ctx.fields.dob,
                   "licence_number": mask_identifier(clean_alnum(number)), "issuing_state": info,
                   "valid_till": valid_till.isoformat() if valid_till else None}
    return v, clean_alnum(number)


async def verify(ctx: DocContext) -> DocumentVerification:
    v, number = verify_sync(ctx)
    if number and not v.failed():
        dob = v.extracted.get("dob")
        await run_external_verification(
            v, "DRIVING_LICENCE", {"document_number": number, "name": ctx.fields.name, "dob": dob},
            label="Licence verified with external provider",
            expected_name=ctx.fields.name, expected_dob=dob, document_text=ctx.full_text,
        )
    return v
