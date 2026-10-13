"""ICAO 9303 TD3 (passport) Machine Readable Zone parsing and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

_WEIGHTS = (7, 3, 1)
_CONFUSED_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
_MRZ_LEN = 44

# ISO 3166-1 alpha-3 plus the ICAO special codes used in MRZs
ICAO_CODES = set("""
ABW AFG AGO AIA ALA ALB AND ARE ARG ARM ASM ATA ATF ATG AUS AUT AZE BDI BEL BEN BES BFA BGD BGR BHR BHS BIH BLM
BLR BLZ BMU BOL BRA BRB BRN BTN BVT BWA CAF CAN CCK CHE CHL CHN CIV CMR COD COG COK COL COM CPV CRI CUB CUW CXR
CYM CYP CZE DEU DJI DMA DNK DOM DZA ECU EGY ERI ESH ESP EST ETH FIN FJI FLK FRA FRO FSM GAB GBR GEO GGY GHA GIB
GIN GLP GMB GNB GNQ GRC GRD GRL GTM GUF GUM GUY HKG HMD HND HRV HTI HUN IDN IMN IND IOT IRL IRN IRQ ISL ISR ITA
JAM JEY JOR JPN KAZ KEN KGZ KHM KIR KNA KOR KWT LAO LBN LBR LBY LCA LIE LKA LSO LTU LUX LVA MAC MAF MAR MCO MDA
MDG MDV MEX MHL MKD MLI MLT MMR MNE MNG MNP MOZ MRT MSR MTQ MUS MWI MYS MYT NAM NCL NER NFK NGA NIC NIU NLD NOR
NPL NRU NZL OMN PAK PAN PCN PER PHL PLW PNG POL PRI PRK PRT PRY PSE PYF QAT REU ROU RUS RWA SAU SDN SEN SGP SGS
SHN SJM SLB SLE SLV SMR SOM SPM SRB SSD STP SUR SVK SVN SWE SWZ SXM SYC SYR TCA TCD TGO THA TJK TKL TKM TLS TON
TTO TUN TUR TUV TWN TZA UGA UKR UMI URY USA UZB VAT VCT VEN VGB VIR VNM VUT WLF WSM YEM ZAF ZMB ZWE
D GBD GBN GBO GBP GBS UNO UNA UNK XXA XXB XXC XXX RKS EUE
""".split())


def char_value(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    if ch == "<":
        return 0
    return ord(ch) - ord("A") + 10


def check_digit(field_text: str) -> int:
    return sum(char_value(c) * _WEIGHTS[i % 3] for i, c in enumerate(field_text)) % 10


def _fix_digits(text: str) -> str:
    return "".join(_CONFUSED_TO_DIGIT.get(c, c) for c in text)


def _yymmdd(value: str, *, kind: str) -> Optional[date]:
    if not re.fullmatch(r"\d{6}", value):
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:])
    today = date.today()
    if kind == "dob":
        year = 1900 + yy if yy > today.year % 100 else 2000 + yy
    else:  # expiry: passports are valid at most ~15y; 20yy covers every live passport
        year = 2000 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


@dataclass
class MrzResult:
    found: bool = False
    structure_ok: bool = False           # two 44-char lines with the expected layout
    lines: tuple[str, str] = ("", "")
    document_code: str = ""
    issuing_country: str = ""
    surname: str = ""
    given_names: str = ""
    passport_number: str = ""
    nationality: str = ""
    dob: Optional[date] = None
    sex: str = ""
    expiry: Optional[date] = None
    personal_number: str = ""
    check_digits: dict[str, bool] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    ocr_corrected: bool = False

    @property
    def checksums_ok(self) -> bool:
        return bool(self.check_digits) and all(self.check_digits.values())


def normalise_mrz_line(line: str) -> str:
    line = line.upper().replace(" ", "")
    for bad in "«‹〈≪‹<":
        line = line.replace(bad, "<")
    return re.sub(r"[^A-Z0-9<]", "", line)


def find_mrz_lines(lines: list[str]) -> Optional[tuple[str, str]]:
    """Locate the two MRZ lines in OCR output (they are adjacent, bottom of the page)."""
    cleaned = [normalise_mrz_line(l) for l in lines]
    for i, l1 in enumerate(cleaned[:-1]):
        if len(l1) >= 30 and l1.startswith("P") and "<<" in l1:
            l2 = cleaned[i + 1]
            if len(l2) >= 30:
                return l1, l2
    # Fallback: an MRZ line broken across OCR boxes — join neighbours until 44 chars
    for i, l1 in enumerate(cleaned):
        if l1.startswith("P<") and "<<" in l1:
            joined = l1
            j = i + 1
            while len(joined) < _MRZ_LEN and j < len(cleaned):
                joined += cleaned[j]
                j += 1
            if len(joined) >= _MRZ_LEN + 30:
                return joined[:_MRZ_LEN], joined[_MRZ_LEN:]
    return None


def parse_td3(line1: str, line2: str) -> MrzResult:
    r = MrzResult(found=True, lines=(line1, line2))
    if len(line1) == _MRZ_LEN - 1:
        line1 += "<"
    if len(line2) != _MRZ_LEN or len(line1) != _MRZ_LEN:
        r.problems.append(f"MRZ lines are {len(line1)}/{len(line2)} characters long; passports use 44/44")
        return r
    if line1[0] != "P":
        r.problems.append("MRZ document code is not 'P' (passport)")
        return r
    r.structure_ok = True

    r.document_code = line1[:2].replace("<", "")
    r.issuing_country = line1[2:5].replace("<", "")
    name_field = line1[5:]
    parts = name_field.split("<<", 1)
    r.surname = parts[0].replace("<", " ").strip()
    r.given_names = (parts[1].replace("<", " ").strip() if len(parts) > 1 else "")

    number = line2[0:9]
    nat = line2[10:13]
    dob_raw, expiry_raw = line2[13:19], line2[21:27]
    r.passport_number = number.replace("<", "")
    r.nationality = nat.replace("<", "")
    r.sex = line2[20].replace("<", "")
    r.personal_number = line2[28:42].replace("<", "")

    def verify_field(name: str, text: str, digit_char: str, numeric: bool) -> str:
        """Check a field's check digit; retry with OCR letter→digit corrections for numeric fields."""
        if not digit_char.isdigit() and digit_char in _CONFUSED_TO_DIGIT:
            digit_char = _CONFUSED_TO_DIGIT[digit_char]
        ok = digit_char.isdigit() and check_digit(text) == int(digit_char)
        if not ok and numeric:
            fixed = _fix_digits(text)
            if digit_char.isdigit() and check_digit(fixed) == int(digit_char):
                r.ocr_corrected = True
                text, ok = fixed, True
        r.check_digits[name] = ok
        if not ok:
            r.problems.append(f"{name.replace('_', ' ')} check digit does not validate")
        return text

    verify_field("passport_number", number, line2[9], numeric=False)
    dob_raw = verify_field("date_of_birth", dob_raw, line2[19], numeric=True)
    expiry_raw = verify_field("expiry_date", expiry_raw, line2[27], numeric=True)
    # Personal number check digit may be '<' (empty field) — then it must be '<' or '0'
    pn_digit = line2[42]
    if r.personal_number == "":
        r.check_digits["personal_number"] = pn_digit in ("<", "0")
        if not r.check_digits["personal_number"]:
            r.problems.append("personal number check digit does not validate")
    else:
        verify_field("personal_number", line2[28:42], pn_digit, numeric=False)
    composite = line2[0:10] + dob_raw + line2[19] + expiry_raw + line2[27] + line2[28:43]
    comp_digit = line2[43]
    comp_ok = comp_digit.isdigit() and check_digit(composite) == int(comp_digit)
    if not comp_ok:   # one of the OCR-corrected fields may be the reason; try the uncorrected line
        raw = line2[0:10] + line2[13:20] + line2[21:43]
        comp_ok = comp_digit.isdigit() and check_digit(raw) == int(comp_digit)
    r.check_digits["composite"] = comp_ok
    if not comp_ok:
        r.problems.append("composite check digit does not validate")

    r.dob = _yymmdd(dob_raw, kind="dob")
    r.expiry = _yymmdd(expiry_raw, kind="expiry")
    if r.dob is None:
        r.problems.append("date of birth is not a valid date")
    if r.expiry is None:
        r.problems.append("expiry date is not a valid date")
    if r.sex not in ("M", "F", ""):
        r.problems.append("sex field is not M, F or <")
    return r


def parse_mrz_from_ocr(lines: list[str]) -> MrzResult:
    found = find_mrz_lines(lines)
    if not found:
        return MrzResult(found=False, problems=["No Machine Readable Zone found"])
    return parse_td3(*found)
