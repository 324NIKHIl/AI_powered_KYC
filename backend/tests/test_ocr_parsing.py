from models.verification import DocumentType
from services.ocr_service import _parse_dob, _parse_id_number
from utils.validators import validate_dob

# Lines as EasyOCR returned them for a bilingual (Kannada) Aadhaar PVC card
CARD = ["Government of India", "Kirtan Shrestha", "Kirtan SoreDoB: 2005", "MALE", "19/11/2023", "7933 0708 5498"]


def test_dob_follows_the_label_not_the_issue_date():
    assert _parse_dob(CARD) == "2005"
    assert _parse_dob(["Aadhaar no. issued: 19/11/2023", "DOB: 15/08/1999"]) == "15/08/1999"
    assert _parse_dob(["Date of Birth: 15 Aug 1999"]) == "15 Aug 1999"


def test_unlabelled_dob_skips_issue_dates():
    assert _parse_dob(["Issue Date: 19/11/2023", "15/08/1999"]) == "15/08/1999"
    assert _parse_dob(["Issued 19/11/2023"]) is None


def test_year_only_dob_is_valid():
    assert validate_dob("2005") and not validate_dob("") and not validate_dob("2999")


def test_aadhaar_number_with_dots_and_noise():
    assert _parse_id_number(["7933.0708.5498"], DocumentType.AADHAAR) == "793307085498"
    # look-alike letters repaired, accepted only because the Verhoeff checksum passes
    assert _parse_id_number(["7933 O7O8 549B"], DocumentType.AADHAAR) == "793307085498"
    assert _parse_id_number(["7933 O7O8 549B 1"], DocumentType.AADHAAR) == "793307085498"
    assert _parse_id_number(["7933 O7O8 5499"], DocumentType.AADHAAR) is None     # checksum fails → not guessed


def test_name_from_split_words_and_multiword_preference():
    from services.ocr_service import _parse_name
    # "Kirtan" / "Shrestha" arrive as separate OCR boxes; a one-word garbage line must not win
    lines = ["Govemmenioklnd", "Kirtan", "Shrestha", "MALE", "7933 0708 5498"]
    assert _parse_name(lines, DocumentType.AADHAAR) == "Kirtan Shrestha"
    assert _parse_name(["Kirtan Shrestha", "Govemmenioklnd"], DocumentType.AADHAAR) == "Kirtan Shrestha"
    assert _parse_name(["Madonna"], DocumentType.AADHAAR) == "Madonna"          # single names still work


def test_tile_pass_decision_and_merge():
    from models.verification import ExtractedFields
    from services.ocr_service import merge_lines, needs_tile_pass
    assert needs_tile_pass(ExtractedFields(name="Govemmenioklnd", dob="2005", id_number="793307085498"))
    assert needs_tile_pass(ExtractedFields(name="Kirtan Shrestha", dob=None, id_number="793307085498"))
    assert not needs_tile_pass(ExtractedFields(name="Kirtan Shrestha", dob="2005", id_number="793307085498"))
    merged, text = merge_lines(["Government of India", "MALE"], ["government of india", "Kirtan Shrestha"])
    assert merged == ["Government of India", "MALE", "Kirtan Shrestha"] and "Kirtan" in text
