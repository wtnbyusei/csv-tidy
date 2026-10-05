"""CSV の解析とヘッダー行の決定（FR-03〜07, FR-25）。"""

import csv
import io
from collections.abc import Sequence

from .errors import CsvSyntaxError
from .models import MAX_BYTES, Record

# 1 つのセルの長さの上限を、ファイルサイズの上限まで引き上げる（FR-06）。
# csv モジュールの既定の上限は 131,072 文字。この設定はプロセス全体に効く。
if csv.field_size_limit() < MAX_BYTES:
    csv.field_size_limit(MAX_BYTES)


def parse(text: str) -> list[Record]:
    """文字列を CSV として解析し、レコードの一覧を返す。

    区切り文字はカンマに固定し、RFC 4180 に沿って解析する（FR-03）。
    書き方の誤り（クォートの閉じ忘れ、閉じたクォートの直後の不正な文字）は
    厳密モードで検出する（FR-05）。空の行は、セルが 0 個のレコードになる。

    Raises:
        CsvSyntaxError: 書き方に誤りがあるとき。`line` は問題のレコードが始まる行。
    """
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    records: list[Record] = []
    last_line = 0
    try:
        for cells in reader:
            records.append(
                Record(
                    index=len(records),
                    line_start=last_line + 1,
                    line_end=reader.line_num,
                    cells=tuple(cells),
                )
            )
            last_line = reader.line_num
    except csv.Error as error:
        # クォートの閉じ忘れはファイルの最後で初めて分かるため、reader.line_num は
        # 最後の行を指す。最後に正しく読めたレコードの次の行を、問題の開始行とする。
        raise CsvSyntaxError(line=last_line + 1, detail=str(error)) from None
    return records


def is_blank(cells: Sequence[str]) -> bool:
    """すべてのセルが空か（セルが 0 個の行も含む）（FR-21 の空行の定義）。"""
    return all(cell == "" for cell in cells)


def find_header(rows: Sequence[Sequence[str]]) -> int | None:
    """最初の空でない行の位置を返す。すべて空なら `None` を返す（FR-04, FR-08）。

    トリムを有効にしているときは、トリム後の値を渡す（FR-21）。
    """
    for position, cells in enumerate(rows):
        if not is_blank(cells):
            return position
    return None
