"""Generate a synthetic product export with deliberate data-quality problems.

All barcodes use the fictional company prefix 8699999 and do not belong to real products.

    python examples/generate_sample.py            # writes examples/sample_products.csv
"""

import csv
from pathlib import Path

PREFIX = "8699999"


def check_digit(body: str) -> str:
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return str((10 - total % 10) % 10)


def ean13(item: int) -> str:
    body = f"{PREFIX}{item:05d}"
    return body + check_digit(body)


def gtin14(unit: str, indicator: int = 1) -> str:
    body = f"{indicator}{unit[:12]}"
    return body + check_digit(body)


def broken_check_digit(code: str) -> str:
    return code[:-1] + str((int(code[-1]) + 3) % 10)


CLEAN = [
    ("DF-1001", "Sucuk Kangal 500 g", 12),
    ("DF-1002", "Sucuk Baton 250 g", 24),
    ("DF-1003", "Pastırma Dilim 120 g", 20),
    ("DF-1004", "Kavurma 400 g", 12),
    ("DF-1005", "Beyaz Peynir 800 g", 6),
    ("DF-1006", "Kaşar Peyniri 400 g", 12),
    ("DF-1007", "Siyah Zeytin 1 kg", 6),
    ("DF-1008", "Yeşil Zeytin 500 g", 12),
    ("DF-1009", "Tahin 300 g", 24),
    ("DF-1010", "Pekmez 700 g", 12),
    ("DF-1011", "Tarhana 500 g", 20),
    ("DF-1012", "Mantı 1 kg", 8),
]


def build_rows():
    rows = []
    for i, (ref, name, qty) in enumerate(CLEAN, start=1):
        unit = ean13(i)
        rows.append([ref, name, unit, gtin14(unit), str(qty)])

    # Extra packaging line for DF-1001 (Odoo-style continuation row): a pallet of 48.
    rows.insert(1, ["", "", "", gtin14(ean13(1), 2), "48"])

    u = {n: ean13(n) for n in range(20, 40)}
    in_store = "210012300000" + check_digit("210012300000")
    rows += [
        ["DF-2001", "Sucuk Kangal 1 kg", broken_check_digit(u[20]), gtin14(u[20]), "6"],
        ["DF-2002", "Pastırma 250 g", "8.69999E+12", "", "12"],
        ["DF-2003", "Kuru Kayısı 500 g", u[22][:5] + "O" + u[22][6:], gtin14(u[22]), "12"],
        ["DF-2004", "Lokum 250 g", u[23][:10], gtin14(u[23]), "24"],
        ["DF-2005", "Imported Olives 340 g", "36000291452", "", "12"],
        ["DF-2006", "Sucuk Dilim 100 g", ean13(2), "", ""],  # duplicate unit of DF-1002
        ["DF-2007", "Kavurma 200 g", u[26], ean13(4), "12"],             # box = unit of DF-1004
        ["DF-2008", "Helva 400 g", u[27], u[27], "12"],                  # same unit and box
        ["DF-2009", "Reçel 380 g", u[28], gtin14(u[29]), "12"],          # GTIN-14 wraps another item
        ["DF-2010", "Bal 450 g", u[30], gtin14(u[30]), ""],              # missing pack qty
        ["DF-2011", "Fındık Ezmesi 350 g", u[31], gtin14(u[31]), "12.5"],
        ["DF-2012", "Limon Sosu 500 ml", u[32], gtin14(u[32]), "1"],
        ["DF-2013", "Nar Ekşisi 250 ml", u[33], "", "12"],               # qty but no box barcode
        ["DF-2014", "Tulum Peyniri 1 kg", "", gtin14(u[34]), "6"],       # no unit barcode
        ["DF-2015", "Pastırma (kg, in-store)", in_store, "", ""],         # restricted circulation
        ["DF-2016", "Pastırma Dilim 240 g", u[36], gtin14(ean13(3)), "20"],  # box duplicate of DF-1003
    ]
    return rows


def main():
    out = Path(__file__).with_name("sample_products.csv")
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Internal Reference", "Name", "Barcode", "Box Barcode", "Units per Box"])
        writer.writerows(build_rows())
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
