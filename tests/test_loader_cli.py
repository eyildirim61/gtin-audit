import pytest

from gtin_audit.cli import main
from gtin_audit.gtin import compute_check_digit
from gtin_audit.loader import LoaderError, load_records, normalize_header, resolve_columns


def make(body: str) -> str:
    return body + str(compute_check_digit(body))


UNIT = make("869999900001")
BOX = make("1" + UNIT[:12])


def test_normalize_header_handles_turkish():
    assert normalize_header("Koli İçi Adet") == "koli ici adet"
    assert normalize_header("ÜRÜN_ADI") == "urun adi"
    assert normalize_header("packaging_ids/barcode") == "packaging ids/barcode"


def test_turkish_semicolon_csv(tmp_path):
    path = tmp_path / "urunler.csv"
    path.write_text(
        "Stok Kodu;Ürün Adı;Barkod;Koli Barkodu;Koli İçi Adet\n"
        f"A1;Pastırma 120 g;{UNIT};{BOX};12\n",
        encoding="utf-8",
    )
    records, used = load_records(path)
    assert used == {
        "ref": "Stok Kodu",
        "name": "Ürün Adı",
        "unit_barcode": "Barkod",
        "box_barcode": "Koli Barkodu",
        "units_per_box": "Koli İçi Adet",
    }
    assert records[0].name == "Pastırma 120 g"
    assert records[0].row == 2


def test_cp1254_encoded_csv(tmp_path):
    path = tmp_path / "eski.csv"
    path.write_bytes("Ürün Adı,Barkod\nŞalgam,{}\n".format(UNIT).encode("cp1254"))
    records, _ = load_records(path)
    assert records[0].name == "Şalgam"


def test_fill_down_for_odoo_packaging_lines(tmp_path):
    second_box = make("2" + UNIT[:12])
    path = tmp_path / "odoo.csv"
    path.write_text(
        "Internal Reference,Name,Barcode,Packagings/Barcode,Packagings/Contained Quantity\n"
        f"A1,Product,{UNIT},{BOX},6\n"
        f",,,{second_box},24\n",
        encoding="utf-8",
    )
    records, _ = load_records(path)
    assert [r.group for r in records] == [1, 1]
    assert records[1].inherited and records[1].unit_barcode == UNIT

    records, _ = load_records(path, fill_down=False)
    assert [r.group for r in records] == [1, 2]


def test_column_override_and_errors(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(f"Code,Weird Column\nA,{UNIT}\n", encoding="utf-8")
    with pytest.raises(LoaderError, match="barcode column"):
        load_records(path)
    records, used = load_records(path, overrides={"unit_barcode": "Weird Column"})
    assert records[0].unit_barcode == UNIT
    with pytest.raises(LoaderError, match="not found"):
        resolve_columns(["a"], {"unit_barcode": "missing"})


def test_unsupported_and_missing_files(tmp_path):
    with pytest.raises(LoaderError):
        load_records(tmp_path / "nope.csv")
    bad = tmp_path / "x.json"
    bad.write_text("{}")
    with pytest.raises(LoaderError, match="Unsupported"):
        load_records(bad)


def test_xlsx_numeric_cells(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Barcode", "Box Barcode", "Units per Box"])
    ws.append([int(UNIT), float(BOX), 12.0])
    path = tmp_path / "p.xlsx"
    wb.save(path)
    records, _ = load_records(path)
    assert records[0].unit_barcode == UNIT
    assert records[0].box_barcode == BOX
    assert records[0].units_per_box == "12"


def test_cli_writes_reports_and_exit_codes(tmp_path, capsys):
    path = tmp_path / "p.csv"
    path.write_text(f"Barcode\n{UNIT}\n123\n", encoding="utf-8")
    out = tmp_path / "out"

    assert main([str(path), "-o", str(out)]) == 0
    assert (out / "report.html").exists()
    csv_text = (out / "issues.csv").read_text(encoding="utf-8-sig")
    assert "INVALID_LENGTH" in csv_text
    assert "1 errors" in capsys.readouterr().out

    assert main([str(path), "-o", str(out), "--fail-on", "error", "-q"]) == 1


def test_cli_reports_loader_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 2
    assert "File not found" in capsys.readouterr().err


def test_html_escapes_values(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text('Name,Barcode\n"<script>x</script>",12\n', encoding="utf-8")
    out = tmp_path / "out"
    main([str(path), "-o", str(out), "-q"])
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_odoo_unit_and_box_barcode_columns(tmp_path):
    path = tmp_path / "odoo_custom.csv"
    path.write_text(
        "Product,Name,Internal Reference,Barcode,Unit,Box Barcode\n"
        f"[A1] P,P,A1,{UNIT},Units,{BOX}\n"
        f"[A2] Q,Q,A2,{make('869999900002')},Case of 12,\n",
        encoding="utf-8",
    )
    records, used = load_records(path)
    assert used["uom"] == "Unit" and used["box_barcode"] == "Box Barcode"
    assert records[0].uom == "Units"
    from gtin_audit.checks import audit
    assert sorted(i.code for i in audit(records)) == ["BOX_BARCODE_ON_SINGLE_UNIT", "MISSING_BOX_BARCODE"]


def test_one_code_column_is_recognised(tmp_path):
    path = tmp_path / "one.csv"
    path.write_text(
        "Internal Reference,Barcode (EAN),Box Barcode,Unit,Same Barcode For Box (Yes/No)\n"
        f"A1,{UNIT},{UNIT},Units,True\n",
        encoding="utf-8",
    )
    records, used = load_records(path)
    assert used["box_is_item"] == "Same Barcode For Box (Yes/No)"
    assert used["unit_barcode"] == "Barcode (EAN)"  # trailing note in parentheses is ignored
    assert records[0].one_code
    from gtin_audit.checks import audit
    assert audit(records) == []
