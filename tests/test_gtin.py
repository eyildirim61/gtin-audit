import pytest

from gtin_audit.gtin import (
    analyze,
    compute_check_digit,
    is_restricted_circulation,
    is_valid_gtin,
    item_gtin_from_case,
)


def make(body: str) -> str:
    return body + str(compute_check_digit(body))


@pytest.mark.parametrize(
    "code",
    [
        "4006381333931",  # EAN-13
        "036000291452",   # UPC-A
        "96385074",       # EAN-8
        make("1869999900001"),  # GTIN-14
    ],
)
def test_known_valid_codes(code):
    assert is_valid_gtin(code)


def test_check_digit_examples():
    assert compute_check_digit("400638133393") == 1
    assert compute_check_digit("03600029145") == 2
    assert compute_check_digit("9638507") == 4


def test_check_digit_rejects_non_digits():
    with pytest.raises(ValueError):
        compute_check_digit("12a4")


def test_bad_check_digit_reports_expected_digit():
    result = analyze("4006381333932")
    assert result.problem == "BAD_CHECK_DIGIT"
    assert "should be 1" in result.detail


def test_whitespace_hyphens_and_float_suffix_are_tolerated():
    assert analyze(" 4006381333931 ").ok
    assert analyze("400-6381-333931").ok
    assert analyze("4006381333931.0").ok


def test_scientific_notation():
    assert analyze("8.69999E+12").problem == "SCIENTIFIC_NOTATION"
    assert analyze("4,00638E+12").problem == "SCIENTIFIC_NOTATION"


def test_invalid_characters():
    result = analyze("40063813339O1")
    assert result.problem == "INVALID_CHARACTERS"
    assert "'O'" in result.detail


def test_invalid_length_with_lost_leading_zero_hint():
    result = analyze("36000291452")  # UPC 036000291452 without its leading zero
    assert result.problem == "INVALID_LENGTH"
    assert "036000291452 is valid" in result.detail


def test_invalid_length_without_hint():
    result = analyze("1234567890")
    assert result.problem == "INVALID_LENGTH"
    assert "leading zero" not in result.detail


def test_normalized_pads_to_14_and_ignores_bad_check_digit():
    assert analyze("036000291452").normalized == "00036000291452"
    assert analyze("4006381333932").normalized == "04006381333932"
    assert analyze("12AB").normalized is None


def test_item_gtin_from_case():
    unit = "4006381333931"
    case = make("1" + unit[:12])
    assert item_gtin_from_case(case) == unit
    assert item_gtin_from_case(make("0" + unit[:12])) is None  # indicator 0
    assert item_gtin_from_case(make("9" + unit[:12])) is None  # variable measure
    assert item_gtin_from_case(unit) is None


@pytest.mark.parametrize(
    "code,expected",
    [
        (make("200123400000"), True),
        (make("41234567890"), True),   # UPC-A with number system 4
        ("4006381333931", False),
        ("96385074", False),           # GTIN-8 not checked
    ],
)
def test_restricted_circulation(code, expected):
    assert is_restricted_circulation(code) is expected
