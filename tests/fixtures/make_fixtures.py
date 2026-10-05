"""テスト用のファイル（テスト計画書 5.2）を作り直すスクリプト。

    uv run python tests/fixtures/make_fixtures.py

作ったファイルはリポジトリに入れる。中身を変えたいときは、このスクリプトを直して実行し直す。
"""

import io
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

HEADER = ["名前", "年齢", "住所", "電話"]
PREFS = ["東京都", "大阪府", "愛知県", "福岡県", "北海道", "京都府", "神奈川県", "広島県"]


def customers(*, with_zwsp: bool) -> list[list[str]]:
    """画面の見本と同じ「顧客一覧」（1,000 行）。

    前後の空白、空行、列数の不一致、見えない文字、重複を 1 つずつ含む。
    ゼロ幅スペース（U+200B）は CP932 で表せないので、CP932 版では入れない。
    """
    rows = [
        HEADER,
        ["山田太郎", "30", "東京都", "03-1111-2222"],
        ["  佐藤花子　", "25", "大阪府", "06-3333-4444"],  # 前後の空白（半角 2 つ、全角 1 つ）
        ["", "", "", ""],  # 空行
        ["鈴木一郎", "41", "愛知県"],  # 列数が足りない
        ["田中​次郎" if with_zwsp else "田中次郎", "28", "福岡県", "092-555-6666"],  # 見えない文字
        ["山田太郎", "30", "東京都", "03-1111-2222"],  # 2 行目と重複
        ["高橋三郎", "52 ", "北海道", "011-777-8888"],  # 後ろの空白
    ]
    number = 9
    while len(rows) < 999:
        address = PREFS[number % len(PREFS)]
        if number == 812:
            address = "東京都千代田区\n丸の内1丁目"  # 複数行にまたがるセル
        rows.append([f"顧客{number:04d}", str(20 + number % 50), address, f"090-{number:04d}-{number * 7 % 10000:04d}"])
        number += 1
    return rows


def to_csv(rows: list[list[str]], newline: str) -> str:
    def cell(value: str) -> str:
        if any(c in value for c in ',"\r\n'):
            return '"' + value.replace('"', '""') + '"'
        return value

    return "".join(",".join(cell(v) for v in row) + newline for row in rows)


def minimal_xlsx() -> bytes:
    """1 つのセルだけの小さな Excel ファイル。"""
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>名前</t></is></c></row></sheetData>'
            "</worksheet>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            # 作り直しても同じバイト列になるよう、日時を固定する
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), content)
    return buffer.getvalue()


def main() -> None:
    files = {
        "customers_cp932.csv": to_csv(customers(with_zwsp=False), "\r\n").encode("cp932"),
        "customers_utf8_bom.csv": to_csv(customers(with_zwsp=True), "\r\n").encode("utf-8-sig"),
        "broken_quote.csv": "名前,メモ\n山田,ok\n\"佐藤,閉じていない\n鈴木,ok\n".encode(),
        "xss.csv": to_csv(
            [["名前", "メモ"], ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>"], ["山田", "<b>太字</b>"]],
            "\n",
        ).encode(),
        "emoji.csv": to_csv([["名前", "メモ"], ["山田😀", "A—B"], ["佐藤", "ok"]], "\n").encode(),
        "not_csv.xlsx": minimal_xlsx(),
    }
    for name, content in files.items():
        (HERE / name).write_bytes(content)
        print(f"{name}: {len(content):,} バイト")


if __name__ == "__main__":
    main()
