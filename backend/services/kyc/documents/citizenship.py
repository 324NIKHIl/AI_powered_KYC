"""
Citizenship-document verification — country-aware.

CitizenshipVerificationService picks a per-country verifier. There is no single
global format, and (for Nepal) no public authoritative API, so unless a provider
is configured the best possible outcome is "document appears valid" — it is never
described as government-verified.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from services.kyc.documents.base import DocContext, start
from services.kyc.external import run_external_verification
from services.kyc.result import CheckOutcome, DocumentVerification, mask_identifier
from services.kyc.text_utils import labelled_value, parse_date


class CountryCitizenshipVerifier(ABC):
    country_code: str = ""
    country_name: str = ""

    @abstractmethod
    def matches(self, ctx: DocContext) -> bool: ...

    @abstractmethod
    def analyse(self, ctx: DocContext, v: DocumentVerification) -> Optional[str]:
        """Add checks + v.extracted. Return the certificate number used for external verification."""


class NepalCitizenshipVerifier(CountryCitizenshipVerifier):
    """Nepal citizenship certificate (नागरिकता प्रमाणपत्र). Dates are printed in Bikram Sambat (BS)."""

    country_code = "NP"
    country_name = "Nepal"
    # Loose: district-ward-year-serial style ("27-01-71-01234"), "1234/056", or 5-14 plain digits
    _NUMBER = re.compile(r"\b(\d{1,3}(?:[-/ ]\d{1,6}){1,4}|\d{5,14})\b")
    _AUTHORITY = ("DISTRICT ADMINISTRATION OFFICE", "CHIEF DISTRICT OFFICER", "DISTRICT ADMINISTRATION", "CDO",
                  "MINISTRY OF HOME AFFAIRS", "GOVERNMENT OF NEPAL")
    BS_MIN, BS_MAX_OFFSET = 1990, 57

    def matches(self, ctx: DocContext) -> bool:
        t = ctx.text_upper
        return "NEPAL" in t or "नेपाल" in ctx.full_text or "नागरिकता" in ctx.full_text

    @staticmethod
    def _labelled(text: str, labels: tuple[str, ...], pattern: str) -> Optional[str]:
        for label in labels:
            m = re.search(label + r"[\s:.\-]*" + pattern, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _bs_year(self, raw: Optional[str]) -> Optional[int]:
        if not raw:
            return None
        m = re.search(r"\b(\d{4})\b", raw)
        return int(m.group(1)) if m else None

    def analyse(self, ctx: DocContext, v: DocumentVerification) -> Optional[str]:
        text = ctx.full_text
        number = self._labelled(text, (r"CITIZENSHIP\s*CERTIFICATE\s*(?:NO|NUMBER)\.?", r"CERTIFICATE\s*(?:NO|NUMBER)\.?",
                                       r"CITIZENSHIP\s*(?:NO|NUMBER)\.?", r"\bNO\.?"), r"([0-9][0-9\-/ ]{3,20}[0-9])")
        if number is None:
            m = self._NUMBER.search(text)
            number = m.group(1) if m else None
        name = labelled_value(ctx.lines, (r"FULL\s*NAME", r"\bNAME\b")) or ctx.fields.name
        dob_raw = self._labelled(text, (r"DATE\s*OF\s*BIRTH", r"\bDOB\b", r"BORN ON"), r"([0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2}|[0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{4})")
        issue_raw = self._labelled(text, (r"ISSUED?\s*(?:ON|DATE)", r"DATE\s*OF\s*ISSUE"), r"([0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2}|[0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{4})")
        district = labelled_value(ctx.lines, (r"\bDISTRICT\b(?!\s+ADMIN)",), r"[A-Za-z]{3,30}")
        address = labelled_value(ctx.lines, (r"PERMANENT\s*ADDRESS", r"\bADDRESS\b"), r"[A-Za-z0-9 ,\-]{4,80}")
        authority = next((a for a in self._AUTHORITY if a in ctx.text_upper), None)

        # Certificate number — plausibility only
        if number and re.fullmatch(r"\d{1,3}(?:[-/ ]\d{1,6}){1,4}|\d{5,14}", number.strip()):
            v.format_valid = True
            v.add("cz_number", "Citizenship number format plausible", CheckOutcome.PASS,
                  "Nepal certificate numbers vary by district and year; only plausibility is checked")
        elif number:
            v.format_valid = False
            v.add("cz_number", "Citizenship number format", CheckOutcome.FAIL, "Number does not look like a Nepal certificate number")
        else:
            v.add("cz_number", "Citizenship number", CheckOutcome.WARN, "Certificate number could not be read")

        # Dates — printed in BS (years ~2000-2085); AD dates tolerated
        current_bs = date.today().year + self.BS_MAX_OFFSET
        by, iy = self._bs_year(dob_raw), self._bs_year(issue_raw)
        for key, label, year in (("cz_dob", "Date of birth plausible", by), ("cz_issue", "Issue date plausible", iy)):
            if year is None:
                v.add(key, label, CheckOutcome.WARN, f"{label.replace(' plausible', '')} could not be read")
            elif (self.BS_MIN <= year <= current_bs) or (1930 <= year <= date.today().year):
                v.add(key, label, CheckOutcome.PASS)
            else:
                v.add(key, label, CheckOutcome.FAIL, f"Year {year} is not plausible for a Bikram Sambat or AD date")
        if by and iy and iy < by + 16 and by > 1990 and iy > 1990:
            v.add("cz_age", "Issued at an eligible age", CheckOutcome.FAIL, "Certificate is dated before the holder turned 16")

        v.add("cz_authority", "Issuing authority identified",
              CheckOutcome.PASS if authority else CheckOutcome.WARN,
              authority.title() if authority else "Issuing authority (e.g. District Administration Office) not found")
        v.add("cz_name", "Name present", CheckOutcome.PASS if name else CheckOutcome.WARN,
              "" if name else "Name could not be read")
        if not ctx.face_extracted:
            v.add("cz_photo", "Photo present", CheckOutcome.WARN, "No face found on the document")

        v.extracted = {"country": self.country_name, "name": name, "citizenship_number": mask_identifier(number and re.sub(r"\W", "", number)),
                       "dob": dob_raw, "address": address or district, "issuing_authority": authority,
                       "issue_date": issue_raw, "calendar": "Bikram Sambat (as printed)"}
        if not re.search(r"[A-Za-z]{4}", text):
            v.add("cz_ocr_language", "Printed in English", CheckOutcome.INFO,
                  "Devanagari text is not read unless OCR_LANGUAGES includes 'ne'")
        return re.sub(r"\s+", "", number) if number else None


class CitizenshipVerificationService:
    """Chooses the country verifier, then runs the (optional) external provider."""

    def __init__(self) -> None:
        self._verifiers: list[CountryCitizenshipVerifier] = [NepalCitizenshipVerifier()]

    def register(self, verifier: CountryCitizenshipVerifier) -> None:
        self._verifiers.append(verifier)

    def select(self, ctx: DocContext) -> Optional[CountryCitizenshipVerifier]:
        return next((x for x in self._verifiers if x.matches(ctx)), None)

    def verify_sync(self, ctx: DocContext) -> tuple[DocumentVerification, Optional[str], Optional[CountryCitizenshipVerifier]]:
        v = start(ctx, "CITIZENSHIP", "Citizenship document")
        verifier = self.select(ctx)
        if verifier is None:
            v.add("cz_country", "Issuing country supported", CheckOutcome.WARN,
                  "No country-specific verifier exists for this citizenship document — manual review required")
            return v, None, None
        v.add("cz_country", "Issuing country identified", CheckOutcome.PASS, verifier.country_name)
        number = verifier.analyse(ctx, v)
        return v, number, verifier

    async def verify(self, ctx: DocContext) -> DocumentVerification:
        v, number, verifier = self.verify_sync(ctx)
        if number and verifier and not v.failed():
            await run_external_verification(
                v, "CITIZENSHIP",
                {"country": verifier.country_code, "document_number": number,
                 "name": v.extracted.get("name"), "dob": v.extracted.get("dob")},
                label="Verified against the government record",
                expected_name=v.extracted.get("name"),
                # BS dates cannot be compared with AD dates by simple parsing
                expected_dob=None,
                document_text=ctx.full_text,
            )
        if not v.authority_unavailable and not v.external_verification and not v.failed():
            v.add("cz_not_government_verified", "Government verification", CheckOutcome.INFO,
                  "Document appears valid — it has NOT been verified by a government source")
        return v


_service = CitizenshipVerificationService()


def get_service() -> CitizenshipVerificationService:
    return _service


async def verify(ctx: DocContext) -> DocumentVerification:
    return await _service.verify(ctx)
