from gtin_audit.checks import RULES, Record, audit, parse_pack_qty, summarize
from gtin_audit.gtin import compute_check_digit


def make(body: str) -> str:
    return body + str(compute_check_digit(body))


def ean(n: int) -> str:
    return make(f"8699999{n:05d}")


def case(unit: str, indicator: int = 1) -> str:
    return make(f"{indicator}{unit[:12]}")


_counter = {"row": 1}


def rec(group=None, **kw) -> Record:
    _counter["row"] += 1
    row = _counter["row"]
    return Record(row=row, group=group if group is not None else row, **kw)


def codes(issues):
    return sorted(i.code for i in issues)


def test_clean_product_has_no_issues():
    u = ean(1)
    assert audit([rec(ref="A", unit_barcode=u, box_barcode=case(u), units_per_box="12")]) == []


def test_missing_unit_barcode():
    assert codes(audit([rec(ref="A")])) == ["MISSING_UNIT_BARCODE"]


def test_bad_unit_barcode_is_reported_with_field():
    issues = audit([rec(ref="A", unit_barcode=ean(1)[:-1] + "0" if ean(1)[-1] != "0" else ean(1)[:-1] + "1")])
    assert codes(issues) == ["BAD_CHECK_DIGIT"]
    assert issues[0].field == "unit_barcode"
    assert issues[0].severity == "error"


def test_duplicate_unit_barcode_across_products():
    u = ean(2)
    issues = audit([rec(ref="A", unit_barcode=u), rec(ref="B", unit_barcode=u)])
    assert codes(issues) == ["DUPLICATE_UNIT_BARCODE", "DUPLICATE_UNIT_BARCODE"]
    assert "B" in issues[0].message


def test_duplicates_detected_across_lengths():
    # a UPC-A and the same code written as EAN-13 with a leading zero are one GTIN
    issues = audit([rec(ref="A", unit_barcode="036000291452"), rec(ref="B", unit_barcode="0036000291452")])
    assert codes(issues) == ["DUPLICATE_UNIT_BARCODE", "DUPLICATE_UNIT_BARCODE"]


def test_duplicate_box_barcode_across_products():
    u1, u2 = ean(3), ean(4)
    box = case(u1)
    issues = audit([
        rec(ref="A", unit_barcode=u1, box_barcode=box, units_per_box="6"),
        rec(ref="B", unit_barcode=u2, box_barcode=box, units_per_box="6"),
    ])
    assert codes(issues).count("DUPLICATE_BOX_BARCODE") == 2


def test_box_of_one_product_is_unit_of_another():
    u1, u2 = ean(5), ean(6)
    issues = audit([
        rec(ref="A", unit_barcode=u1),
        rec(ref="B", unit_barcode=u2, box_barcode=u1, units_per_box="12"),
    ])
    assert codes(issues) == ["UNIT_BOX_COLLISION", "UNIT_BOX_COLLISION"]


def test_same_unit_and_box():
    u = ean(7)
    issues = audit([rec(ref="A", unit_barcode=u, box_barcode=u, units_per_box="12")])
    assert codes(issues) == ["SAME_UNIT_AND_BOX"]


def test_gtin14_box_wrapping_another_item():
    issues = audit([rec(ref="A", unit_barcode=ean(8), box_barcode=case(ean(9)), units_per_box="12")])
    assert codes(issues) == ["BOX_GTIN14_MISMATCH"]
    assert ean(9) in issues[0].message


def test_gtin13_box_barcode_is_not_compared_structurally():
    issues = audit([rec(ref="A", unit_barcode=ean(10), box_barcode=ean(11), units_per_box="12")])
    assert issues == []


def test_pack_quantity_rules():
    u = ean(12)
    assert codes(audit([rec(unit_barcode=u, box_barcode=case(u))])) == ["MISSING_PACK_QTY"]
    assert codes(audit([rec(unit_barcode=u, box_barcode=case(u), units_per_box="1")])) == ["PACK_QTY_ONE"]
    assert codes(audit([rec(unit_barcode=u, box_barcode=case(u), units_per_box="12.5")])) == ["INVALID_PACK_QTY"]
    assert codes(audit([rec(unit_barcode=u, box_barcode=case(u), units_per_box="-3")])) == ["INVALID_PACK_QTY"]
    assert codes(audit([rec(unit_barcode=u, units_per_box="12")])) == ["MISSING_BOX_BARCODE"]
    assert audit([rec(unit_barcode=u, units_per_box="1")]) == []


def test_parse_pack_qty():
    assert parse_pack_qty("12") == (12, False)
    assert parse_pack_qty("12.0") == (12, False)
    assert parse_pack_qty("12,0") == (12, False)
    assert parse_pack_qty("") == (None, False)
    assert parse_pack_qty("abc") == (None, True)
    assert parse_pack_qty("0") == (None, True)


def test_restricted_circulation_is_info():
    issues = audit([rec(unit_barcode=make("210012300000"))])
    assert codes(issues) == ["RESTRICTED_CIRCULATION"]
    assert issues[0].severity == "info"


def test_extra_packaging_lines_share_a_product():
    u = ean(13)
    first = rec(ref="A", unit_barcode=u, box_barcode=case(u, 1), units_per_box="6")
    second = rec(group=first.group, ref="A", unit_barcode=u, box_barcode=case(u, 2), units_per_box="24", inherited=True)
    assert audit([first, second]) == []


def test_same_box_twice_on_one_product():
    u = ean(14)
    first = rec(ref="A", unit_barcode=u, box_barcode=case(u), units_per_box="6")
    second = rec(group=first.group, ref="A", unit_barcode=u, box_barcode=case(u), units_per_box="24", inherited=True)
    assert codes(audit([first, second])) == ["DUPLICATE_BOX_BARCODE", "DUPLICATE_BOX_BARCODE"]


def test_issues_sorted_by_severity_then_row():
    issues = audit([
        rec(unit_barcode=make("210012300000")),   # info
        rec(),                                      # warning
        rec(unit_barcode="123"),                    # error
    ])
    assert [i.severity for i in issues] == ["error", "warning", "info"]


def test_every_rule_has_known_severity():
    assert {sev for sev, _ in RULES.values()} <= {"error", "warning", "info"}


def test_summarize_counts():
    issues = audit([rec(), rec(unit_barcode="123")])
    summary = summarize(issues)
    assert summary["by_severity"] == {"error": 1, "warning": 1, "info": 0}
    assert summary["by_code"] == {"INVALID_LENGTH": 1, "MISSING_UNIT_BARCODE": 1}


# --- unit of measure ("Case of 12") ---------------------------------------------------

from gtin_audit.checks import uom_quantity  # noqa: E402


def test_uom_quantity():
    assert uom_quantity("Case of 12") == 12
    assert uom_quantity("Pack of 6") == 6
    assert uom_quantity("case of 9") == 9
    assert uom_quantity("Koli 24") == 24
    assert uom_quantity("Units") == 1
    assert uom_quantity("Dozens") == 12
    assert uom_quantity("kg") is None
    assert uom_quantity("") is None


def test_box_qty_read_from_uom():
    u = ean(15)
    assert audit([rec(unit_barcode=u, box_barcode=case(u), uom="Case of 12")]) == []


def test_box_barcode_on_single_unit_uom():
    u = ean(16)
    issues = audit([rec(unit_barcode=u, box_barcode=case(u), uom="Units")])
    assert codes(issues) == ["BOX_BARCODE_ON_SINGLE_UNIT"]
    assert issues[0].field == "uom" and issues[0].severity == "warning"


def test_case_uom_without_box_barcode_is_info():
    issues = audit([rec(unit_barcode=ean(17), uom="Case of 12")])
    assert codes(issues) == ["MISSING_BOX_BARCODE"]
    assert "Case of 12" in issues[0].message


def test_units_uom_without_box_barcode_is_fine():
    assert audit([rec(unit_barcode=ean(18), uom="Units")]) == []


def test_unreadable_uom_with_box_barcode():
    u = ean(19)
    issues = audit([rec(unit_barcode=u, box_barcode=case(u), uom="kg")])
    assert codes(issues) == ["MISSING_PACK_QTY"]
    assert issues[0].field == "uom"


def test_units_per_box_column_wins_over_uom():
    u = ean(21)
    assert audit([rec(unit_barcode=u, box_barcode=case(u), units_per_box="6", uom="Units")]) == []


def test_no_box_column_skips_missing_box_barcode():
    assert audit([rec(unit_barcode=ean(22), uom="Case of 12")], has_box_column=False) == []


# --- one code (box = item) flag -----------------------------------------------------------

from gtin_audit.checks import parse_flag  # noqa: E402


def test_parse_flag():
    for v in ("True", "1", "yes", "Evet", "x", " TRUE "):
        assert parse_flag(v)
    for v in ("False", "0", "", "no", "Hayır"):
        assert not parse_flag(v)


def test_one_code_allows_same_unit_and_box():
    u = ean(23)
    assert audit([rec(unit_barcode=u, box_barcode=u, uom="Units", box_is_item="True")]) == []


def test_without_flag_same_unit_and_box_is_still_an_error():
    u = ean(24)
    issues = audit([rec(unit_barcode=u, box_barcode=u, uom="Units", box_is_item="False")])
    assert "SAME_UNIT_AND_BOX" in codes(issues)


def test_one_code_with_different_box_barcode_is_flagged():
    u = ean(25)
    issues = audit([rec(unit_barcode=u, box_barcode=case(u), uom="Units", box_is_item="1")])
    assert codes(issues) == ["ONE_CODE_MISMATCH"]


def test_one_code_without_box_barcode_is_fine():
    assert audit([rec(unit_barcode=ean(26), uom="Case of 12", box_is_item="True")]) == []


def test_one_code_box_with_note_still_reports_the_note():
    u = ean(27)
    issues = audit([rec(unit_barcode=u, box_barcode=f"{u} (same as UPC)", uom="Units", box_is_item="True")])
    assert codes(issues) == ["INVALID_CHARACTERS"]
