"""GTIN / EAN / UPC helpers based on the GS1 mod-10 check digit algorithm."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

VALID_LENGTHS = (8, 12, 13, 14)

_SCIENTIFIC = re.compile(r"^\d+(?:[.,]\d+)?[eE]\+?\d+$")
_SEPARATORS = re.compile(r"[\s\-]")


def compute_check_digit(body: str) -> int:
    """Return the GS1 check digit for ``body`` (all digits except the check digit).

    Weights alternate 3, 1, 3, ... starting from the rightmost digit of the body.
    """
    if not body or not body.isdigit():
        raise ValueError(f"body must be a non-empty string of digits, got {body!r}")
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def is_valid_gtin(code: str) -> bool:
    return analyze(code).ok


@dataclass(frozen=True)
class GtinCheck:
    """Result of analysing one raw barcode value."""

    raw: str
    digits: str
    problem: Optional[str] = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.problem is None

    @property
    def normalized(self) -> Optional[str]:
        """14-digit form used to compare barcodes of different lengths.

        Returned whenever the value is all digits with a valid GTIN length, even if the
        check digit is wrong, so duplicates are still detected.
        """
        if self.digits.isdigit() and len(self.digits) in VALID_LENGTHS:
            return self.digits.zfill(14)
        return None


def analyze(raw) -> GtinCheck:
    """Analyse a raw barcode value as it came out of a spreadsheet or ERP export."""
    raw_str = "" if raw is None else str(raw)
    value = raw_str.strip()

    if not value:
        return GtinCheck(raw_str, "", "EMPTY", "No barcode.")

    if _SCIENTIFIC.match(value):
        return GtinCheck(
            raw_str,
            "",
            "SCIENTIFIC_NOTATION",
            f"'{value}' looks like spreadsheet scientific notation; the real digits are lost "
            "and must be re-entered from the source.",
        )

    digits = _SEPARATORS.sub("", value)
    if digits.endswith(".0") and digits[:-2].isdigit():
        digits = digits[:-2]  # number stored as float, e.g. 8690000000017.0

    if not digits.isdigit():
        bad = sorted({c for c in digits if not c.isdigit()})
        return GtinCheck(
            raw_str,
            digits,
            "INVALID_CHARACTERS",
            f"Contains non-digit characters: {' '.join(repr(c) for c in bad)}.",
        )

    if len(digits) not in VALID_LENGTHS:
        detail = f"{len(digits)} digits; a GTIN has 8, 12, 13 or 14."
        padded = "0" + digits
        if len(padded) in VALID_LENGTHS and _check_digit_ok(padded):
            detail += f" Probably a lost leading zero: {padded} is valid."
        return GtinCheck(raw_str, digits, "INVALID_LENGTH", detail)

    expected = compute_check_digit(digits[:-1])
    if int(digits[-1]) != expected:
        return GtinCheck(
            raw_str,
            digits,
            "BAD_CHECK_DIGIT",
            f"Check digit is {digits[-1]} but should be {expected}. "
            "The error may be in any digit, so verify against the label.",
        )

    return GtinCheck(raw_str, digits)


def _check_digit_ok(digits: str) -> bool:
    return int(digits[-1]) == compute_check_digit(digits[:-1])


def item_gtin_from_case(gtin14: str) -> Optional[str]:
    """Return the GTIN-13 that a GTIN-14 case code is built from.

    For indicator digits 1-8, a GTIN-14 is ``indicator + first 12 digits of the item GTIN-13
    + new check digit``. Indicator 0 and 9 (variable measure) do not follow this pattern.
    """
    if len(gtin14) != 14 or not gtin14.isdigit() or gtin14[0] not in "12345678":
        return None
    body = gtin14[1:13]
    return body + str(compute_check_digit(body))


def is_restricted_circulation(digits: str) -> bool:
    """True for GS1 prefixes reserved for in-store / variable-weight use (020-029, 040-049, 200-299).

    Only applied to 12/13-digit codes; GTIN-8 uses different rules.
    """
    if len(digits) not in (12, 13) or not digits.isdigit():
        return False
    gtin13 = digits.zfill(13)
    return gtin13.startswith(("02", "04", "2"))
