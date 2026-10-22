"""Audit rules for product master data (unit barcodes, box barcodes, pack quantities)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .gtin import GtinCheck, analyze, is_restricted_circulation, item_gtin_from_case

# code -> (severity, one-line description)
RULES: Dict[str, Tuple[str, str]] = {
    "SCIENTIFIC_NOTATION": ("error", "Barcode was turned into scientific notation (e.g. 8.69E+12) by a spreadsheet"),
    "INVALID_CHARACTERS": ("error", "Barcode contains non-digit characters"),
    "INVALID_LENGTH": ("error", "Barcode length is not 8, 12, 13 or 14 digits"),
    "BAD_CHECK_DIGIT": ("error", "GS1 check digit is wrong"),
    "DUPLICATE_UNIT_BARCODE": ("error", "Same unit barcode is used by more than one product"),
    "DUPLICATE_BOX_BARCODE": ("error", "Same box barcode is used more than once"),
    "UNIT_BOX_COLLISION": ("error", "A box barcode of one product is the unit barcode of another"),
    "SAME_UNIT_AND_BOX": ("error", "Unit and box barcode of a product are identical"),
    "INVALID_PACK_QTY": ("error", "Units-per-box is not a positive whole number"),
    "BOX_GTIN14_MISMATCH": ("warning", "GTIN-14 box barcode does not wrap this product's unit barcode"),
    "MISSING_UNIT_BARCODE": ("warning", "Product has no unit barcode"),
    "MISSING_PACK_QTY": ("warning", "Box barcode is set but the number of units in the box is unknown"),
    "PACK_QTY_ONE": ("warning", "Box barcode with units-per-box = 1"),
    "BOX_BARCODE_ON_SINGLE_UNIT": ("warning", "Box barcode is set but the unit of measure is a single unit (e.g. 'Units')"),
    "ONE_CODE_MISMATCH": ("warning", "Product is flagged 'box = item' (one code) but its box barcode differs from the unit barcode"),
    "MISSING_BOX_BARCODE": ("info", "Box holds more than 1 unit but has no box barcode"),
    "RESTRICTED_CIRCULATION": ("info", "Barcode is in a GS1 in-store / variable-weight range (020-029, 040-049, 200-299)"),
}

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

_FIELD_FOR_KIND = {"unit": "unit_barcode", "box": "box_barcode"}


@dataclass
class Record:
    """One row of the input. ``group`` identifies the product (several rows may share it)."""

    row: int
    group: int
    ref: str = ""
    name: str = ""
    unit_barcode: str = ""
    box_barcode: str = ""
    units_per_box: str = ""
    uom: str = ""  # unit of measure, e.g. "Units", "Case of 12"
    box_is_item: str = ""  # "one code" flag: the box carries the same barcode as the unit, on purpose
    inherited: bool = False

    @property
    def one_code(self) -> bool:
        return parse_flag(self.box_is_item)  # True for extra packaging lines that inherited the product fields

    @property
    def label(self) -> str:
        return self.ref or self.name or f"row {self.row}"


@dataclass
class Issue:
    row: int
    severity: str
    code: str
    field: str
    value: str
    ref: str
    name: str
    message: str


def _issue(rec: Record, code: str, field: str, value: str, message: str) -> Issue:
    return Issue(rec.row, RULES[code][0], code, field, value, rec.ref, rec.name, message)


def parse_pack_qty(value: str) -> Tuple[Optional[int], bool]:
    """Return (quantity, is_invalid). Empty input gives (None, False)."""
    text = (value or "").strip()
    if not text:
        return None, False
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return None, True
    if number <= 0 or not number.is_integer():
        return None, True
    return int(number), False


_TRUE_VALUES = {"true", "1", "yes", "y", "t", "x", "evet", "e", "var", "✓", "✔"}


def parse_flag(value: str) -> bool:
    """Spreadsheet-style boolean: True/1/Yes/Evet/x are true; anything else (including empty) is false."""
    return (value or "").strip().casefold() in _TRUE_VALUES


_UOM_PACK = re.compile(r"\b(?:case|pack|box|carton|koli|paket)\s*(?:of|x)?\s*(\d+)\b", re.IGNORECASE)
_UOM_SINGLE = {"unit", "units", "unit(s)", "pc", "pcs", "piece", "pieces", "ea", "each", "adet"}
_UOM_DOZEN = {"dozen", "dozens"}


def uom_quantity(uom: str) -> Optional[int]:
    """Units contained in a unit of measure: 'Case of 12' -> 12, 'Units' -> 1, 'kg' -> None."""
    text = (uom or "").strip()
    if not text:
        return None
    match = _UOM_PACK.search(text)
    if match:
        return int(match.group(1)) or None
    lowered = text.casefold()
    if lowered in _UOM_SINGLE:
        return 1
    if lowered in _UOM_DOZEN:
        return 12
    return None


def _barcode_issues(rec: Record, field: str, check: GtinCheck) -> List[Issue]:
    if check.problem:
        return [_issue(rec, check.problem, field, check.raw, check.detail)]
    if is_restricted_circulation(check.digits):
        return [
            _issue(
                rec,
                "RESTRICTED_CIRCULATION",
                field,
                check.raw,
                f"{check.digits} is in a range reserved for in-store or variable-weight codes; "
                "fine for internal use, not valid across retailers.",
            )
        ]
    return []


def _row_issues(
    rec: Record, occurrences: Dict[str, List[Tuple[Record, str]]], has_box_column: bool = True
) -> List[Issue]:
    issues: List[Issue] = []

    unit: Optional[GtinCheck] = None
    if rec.unit_barcode.strip():
        unit = analyze(rec.unit_barcode)
        if not rec.inherited:  # the product's own row reports unit problems once
            issues += _barcode_issues(rec, "unit_barcode", unit)
            if unit.normalized:
                occurrences[unit.normalized].append((rec, "unit"))
    elif not rec.inherited:
        issues.append(_issue(rec, "MISSING_UNIT_BARCODE", "unit_barcode", "", "No unit barcode."))

    box: Optional[GtinCheck] = None
    if rec.box_barcode.strip():
        box = analyze(rec.box_barcode)
        issues += _barcode_issues(rec, "box_barcode", box)
        if box.normalized:
            occurrences[box.normalized].append((rec, "box"))

    # Box quantity comes from the units-per-box column when filled, otherwise from the unit of measure.
    qty, qty_invalid = parse_pack_qty(rec.units_per_box)
    qty_source: Optional[str] = "column" if rec.units_per_box.strip() else None
    if qty_source is None:
        uom_qty = uom_quantity(rec.uom)
        if uom_qty is not None:
            qty, qty_source = uom_qty, "uom"
    if qty_invalid:
        issues.append(
            _issue(
                rec,
                "INVALID_PACK_QTY",
                "units_per_box",
                rec.units_per_box,
                f"'{rec.units_per_box}' is not a positive whole number.",
            )
        )

    one_code = rec.one_code  # box intentionally carries the unit barcode: no box quantity rules apply

    if box is not None:
        if one_code:
            pass
        elif qty_source is None:
            if rec.uom.strip():
                message = f"Box barcode is set but the box quantity cannot be read from unit of measure '{rec.uom}'."
                issues.append(_issue(rec, "MISSING_PACK_QTY", "uom", rec.uom, message))
            else:
                message = "Box barcode is set but units-per-box is empty."
                issues.append(_issue(rec, "MISSING_PACK_QTY", "units_per_box", "", message))
        elif qty == 1 and qty_source == "column":
            issues.append(
                _issue(
                    rec,
                    "PACK_QTY_ONE",
                    "units_per_box",
                    rec.units_per_box,
                    "A box that holds 1 unit usually means the quantity was never filled in.",
                )
            )
        elif qty == 1:
            issues.append(
                _issue(
                    rec,
                    "BOX_BARCODE_ON_SINGLE_UNIT",
                    "uom",
                    rec.uom,
                    f"Unit of measure is '{rec.uom}', so how many units the box holds is not recorded.",
                )
            )

        if unit is not None and unit.normalized and box.normalized:
            if one_code:
                if unit.normalized != box.normalized:
                    issues.append(
                        _issue(
                            rec,
                            "ONE_CODE_MISMATCH",
                            "box_barcode",
                            rec.box_barcode,
                            f"Flagged as one code (box = item), but box barcode {box.digits} "
                            f"is not the unit barcode {unit.digits}.",
                        )
                    )
            elif unit.normalized == box.normalized:
                issues.append(
                    _issue(
                        rec,
                        "SAME_UNIT_AND_BOX",
                        "box_barcode",
                        rec.box_barcode,
                        "Scanning the box would book a single unit instead of a full box.",
                    )
                )
            elif unit.ok and box.ok and len(box.digits) == 14:
                inner = item_gtin_from_case(box.digits)
                if inner is not None and inner.zfill(14) != unit.normalized:
                    issues.append(
                        _issue(
                            rec,
                            "BOX_GTIN14_MISMATCH",
                            "box_barcode",
                            rec.box_barcode,
                            f"Box GTIN-14 {box.digits} is built from item {inner}, "
                            f"but this product's unit barcode is {unit.digits}.",
                        )
                    )
    elif has_box_column and not one_code and qty is not None and qty > 1:
        source = f"unit of measure '{rec.uom}'" if qty_source == "uom" else "units-per-box"
        issues.append(
            _issue(
                rec,
                "MISSING_BOX_BARCODE",
                "box_barcode",
                "",
                f"Box holds {qty} units ({source}) but there is no box barcode to scan.",
            )
        )

    return issues


def _describe(rec: Record, kind: str) -> str:
    return f"row {rec.row} ({rec.label}, {kind})"


def _duplicate_issues(occurrences: Dict[str, List[Tuple[Record, str]]]) -> List[Issue]:
    issues: List[Issue] = []
    for occ in occurrences.values():
        if len(occ) < 2:
            continue
        groups = {rec.group for rec, _ in occ}

        if len(groups) > 1:
            kinds = {kind for _, kind in occ}
            if kinds == {"unit"}:
                code = "DUPLICATE_UNIT_BARCODE"
            elif kinds == {"box"}:
                code = "DUPLICATE_BOX_BARCODE"
            else:
                code = "UNIT_BOX_COLLISION"
            for rec, kind in occ:
                others = [(o, k) for o, k in occ if o.group != rec.group]
                listed = ", ".join(_describe(o, k) for o, k in others[:5])
                if len(others) > 5:
                    listed += f" and {len(others) - 5} more"
                field = _FIELD_FOR_KIND[kind]
                issues.append(_issue(rec, code, field, getattr(rec, field), f"Also used at {listed}."))
            continue

        boxes = [(rec, kind) for rec, kind in occ if kind == "box"]
        if len(boxes) > 1:
            for rec, _ in boxes:
                others = [o for o, _ in boxes if o is not rec]
                listed = ", ".join(f"row {o.row}" for o in others)
                issues.append(
                    _issue(
                        rec,
                        "DUPLICATE_BOX_BARCODE",
                        "box_barcode",
                        rec.box_barcode,
                        f"Same box barcode on another packaging line of this product ({listed}).",
                    )
                )
    return issues


def audit(records: Iterable[Record], has_box_column: bool = True) -> List[Issue]:
    """Run every rule over the records and return issues sorted by severity, then row.

    ``has_box_column=False`` means the input has no box barcode column at all, so missing
    box barcodes are not reported (they were never exported, not necessarily missing).
    """
    occurrences: Dict[str, List[Tuple[Record, str]]] = defaultdict(list)
    issues: List[Issue] = []
    for rec in records:
        issues += _row_issues(rec, occurrences, has_box_column)
    issues += _duplicate_issues(occurrences)
    issues.sort(key=lambda i: (SEVERITY_ORDER[i.severity], i.row, i.code))
    return issues


def summarize(issues: Iterable[Issue]) -> Dict[str, Dict[str, int]]:
    by_severity: Dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    by_code: Dict[str, int] = defaultdict(int)
    for issue in issues:
        by_severity[issue.severity] += 1
        by_code[issue.code] += 1
    return {"by_severity": by_severity, "by_code": dict(by_code)}
