"""
10th / 12th result-document verification.
OCR → structured extraction → arithmetic/consistency validation → external verification.
"Result successfully extracted" is not "result verified with the board".
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from services.kyc.documents.base import DocContext, start
from services.kyc.external import run_external_verification
from services.kyc.result import CheckOutcome, DocumentVerification, mask_identifier
from services.kyc.text_utils import labelled_value

BOARDS = (
    ("CENTRAL BOARD OF SECONDARY EDUCATION", "Central Board of Secondary Education"),
    ("CBSE", "Central Board of Secondary Education"), ("CISCE", "CISCE"), ("ICSE", "CISCE (ICSE)"),
    ("ISC", "CISCE (ISC)"), ("NIOS", "NIOS"), ("BOARD OF SECONDARY EDUCATION", "State Board of Secondary Education"),
    ("BOARD OF SCHOOL EDUCATION", "State Board of School Education"), ("HIGHER SECONDARY", "Higher Secondary Board"),
    ("NATIONAL EXAMINATIONS BOARD", "National Examinations Board (Nepal)"), ("SECONDARY EDUCATION EXAMINATION", "SEE (Nepal)"),
    ("SCHOOL LEVEL CERTIFICATE", "SLC (Nepal)"), ("UNIVERSITY", "University"),
)
_LEVEL_12 = ("SENIOR SECONDARY", "CLASS XII", "CLASS 12", "XII", "HSC", "INTERMEDIATE", "HIGHER SECONDARY", "PLUS TWO", "+2", "ISC")
_LEVEL_10 = ("SECONDARY SCHOOL", "CLASS X", "CLASS 10", "SSC", "SSLC", "MATRIC", "HIGH SCHOOL", "SLC", "SEE", "ICSE")
_SUBJECT_LINE = re.compile(
    r"^(?:\d{3}\s+)?([A-Za-z][A-Za-z &.\-/()]{2,40}?)\s+(\d{1,3})\s+(\d{1,3})(?:\s+(\d{1,3}))?(?:\s+[A-Z0-9+]{1,3})?$"
)


def parse_subjects(lines: list[str]) -> list[dict]:
    """Rows like 'MATHEMATICS 100 95' / 'ENGLISH 80 72 …' → {subject, max, obtained}."""
    subjects = []
    for line in lines:
        m = _SUBJECT_LINE.match(line.strip())
        if not m:
            continue
        name, a, b = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        if any(w in name.upper() for w in ("TOTAL", "PERCENT", "ROLL", "YEAR", "MARKS", "RESULT")):
            continue
        # Column order varies: treat the larger of the first two numbers as the maximum
        maximum, obtained = (a, b) if a >= b else (b, a)
        subjects.append({"subject": name.title(), "max": maximum, "obtained": obtained})
    return subjects


def _find(text: str, patterns: tuple[str, ...]) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def verify_sync(ctx: DocContext) -> tuple[DocumentVerification, dict]:
    v = start(ctx, "EDUCATION", "Education certificate")
    text, upper = ctx.full_text, ctx.text_upper

    roll = _find(text, (r"(?:ROLL|SEAT|REGISTRATION|SYMBOL|REG)\.?\s*(?:NO|NUMBER)?\.?[\s:.\-]*([A-Z0-9][A-Z0-9/\-]{4,19})",))
    name = labelled_value(ctx.lines, (r"NAME OF (?:THE )?(?:STUDENT|CANDIDATE)", r"CANDIDATE'?S? NAME",
                                       r"STUDENT'?S? NAME", r"\bNAME\b")) or ctx.fields.name
    year_s = _find(text, (r"(?:EXAMINATION|EXAM|YEAR|SESSION|PASSING)[^0-9]{0,25}((?:19|20)\d{2})", r"\b((?:19|20)\d{2})\b"))
    board = next((label for key, label in BOARDS if key in upper), None)
    institution = labelled_value(ctx.lines, (r"(?:SCHOOL|INSTITUTION|COLLEGE)(?: NAME)?\s*[:\-]",), r"[A-Za-z][A-Za-z .,&'\-]{4,70}")
    level = "12th" if any(k in upper for k in _LEVEL_12) else "10th" if any(k in upper for k in _LEVEL_10) else None
    percentage_s = _find(text, (r"PERCENTAGE[\s:.\-]*(\d{1,3}(?:\.\d{1,2})?)", r"(\d{1,3}(?:\.\d{1,2})?)\s*%"))
    total_s = _find(text, (r"GRAND TOTAL[\s:.\-]*(\d{2,4})", r"TOTAL(?: MARKS)?(?: OBTAINED)?[\s:.\-]*(\d{2,4})"))
    subjects = parse_subjects(ctx.lines)

    # ── Structured extraction completeness ────────────────────────────────────
    missing = [k for k, val in (("student name", name), ("roll/registration number", roll), ("board", board),
                                ("year", year_s), ("exam level", level)) if not val]
    v.add("edu_extraction", "Key result fields extracted",
          CheckOutcome.PASS if not missing else CheckOutcome.WARN,
          "" if not missing else "Could not read: " + ", ".join(missing))
    v.add("edu_roll", "Roll / registration number present", CheckOutcome.PASS if roll else CheckOutcome.WARN,
          "" if roll else "Roll/registration number is needed to verify the result with the board")
    v.add("edu_board", "Examining body identified", CheckOutcome.PASS if board else CheckOutcome.WARN,
          board or "Board/university not recognised")

    year = int(year_s) if year_s else None
    if year is not None:
        if 1950 <= year <= date.today().year:
            v.add("edu_year", "Examination year plausible", CheckOutcome.PASS, str(year))
        else:
            v.add("edu_year", "Examination year plausible", CheckOutcome.FAIL, f"Year {year} is not plausible")

    # ── Arithmetic consistency ────────────────────────────────────────────────
    arithmetic_ran = False
    bad = [s for s in subjects if s["obtained"] > s["max"]]
    if subjects:
        arithmetic_ran = True
        if bad:
            v.add("edu_marks", "Marks arithmetic consistent", CheckOutcome.FAIL,
                  "Marks obtained exceed the maximum for: " + ", ".join(s["subject"] for s in bad))
    total = int(total_s) if total_s else None
    sum_obtained = sum(s["obtained"] for s in subjects)
    sum_max = sum(s["max"] for s in subjects)
    if subjects and total is not None and len(subjects) >= 3 and not bad:
        if total == sum_obtained:
            v.add("edu_marks", "Marks arithmetic consistent", CheckOutcome.PASS, "Subject marks add up to the printed total")
        elif sum_obtained * 0.7 <= total < sum_obtained:
            # Some boards print a best-of-N total, which is lower than the sum of every listed subject
            v.add("edu_marks", "Marks arithmetic consistent", CheckOutcome.WARN,
                  f"Printed total ({total}) is lower than the sum of listed subjects ({sum_obtained})")
        else:
            v.add("edu_marks", "Marks arithmetic consistent", CheckOutcome.FAIL,
                  f"Printed total ({total}) does not match the subject marks ({sum_obtained})")
    elif subjects and not bad:
        v.add("edu_marks", "Marks arithmetic consistent", CheckOutcome.WARN, "Not enough rows to cross-check the total")
    elif not arithmetic_ran:
        v.add("edu_marks", "Marks arithmetic consistent", CheckOutcome.SKIP, "Subject marks could not be read")

    if percentage_s and total is not None and sum_max and not bad:
        pct = float(percentage_s)
        computed = 100.0 * total / sum_max
        if abs(pct - computed) <= 1.0:
            v.add("edu_percentage", "Percentage consistent with total", CheckOutcome.PASS)
        else:
            v.add("edu_percentage", "Percentage consistent with total", CheckOutcome.FAIL,
                  f"Printed {pct:.1f}% but total/maximum gives {computed:.1f}%")
    elif percentage_s and float(percentage_s) > 100:
        v.add("edu_percentage", "Percentage plausible", CheckOutcome.FAIL, "Percentage exceeds 100%")

    v.format_valid = None if not v.checks else (not v.failed() and bool(roll))
    v.extracted = {
        "name": name, "roll_number": mask_identifier(roll), "board": board, "institution": institution,
        "level": level, "year": year, "subjects": subjects, "total_marks": total, "percentage": percentage_s,
    }
    return v, {"roll": roll, "name": name, "board": board, "year": year, "level": level,
               "total": total, "percentage": percentage_s}


async def verify(ctx: DocContext) -> DocumentVerification:
    v, info = verify_sync(ctx)
    if info["roll"] and not v.failed():
        await run_external_verification(
            v, "EDUCATION",
            {"document_number": info["roll"], "name": info["name"], "board": info["board"],
             "year": info["year"], "level": info["level"], "total_marks": info["total"], "percentage": info["percentage"]},
            label="Result verified with the examining body",
            expected_name=info["name"], expected_dob=None, document_text=ctx.full_text,
        )
    if not v.external_verification and not v.failed():
        v.add("edu_not_verified", "Verified against the board's records", CheckOutcome.INFO,
              "Result was read from the document; it has not been confirmed with the examining body")
    return v
