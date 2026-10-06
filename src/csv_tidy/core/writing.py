"""CSV の書き出し（FR-14, FR-15, FR-50）と、変更の記録から整形後の値を組み立てる処理。"""

import csv
import io
from collections.abc import Sequence

from .models import CellTrimmed, FormulaEscaped, Newline, OutputEncoding, RowRemoved, TidyResult

_CODECS = {
    OutputEncoding.UTF8: "utf-8",
    OutputEncoding.UTF8_BOM: "utf-8-sig",  # 先頭に BOM を付ける（Excel 向け）
    OutputEncoding.CP932: "cp932",
}
_LINE_TERMINATORS = {Newline.LF: "\n", Newline.CRLF: "\r\n"}


def write_csv(rows: Sequence[Sequence[str]], encoding: OutputEncoding, newline: Newline) -> bytes:
    """表を CSV のバイト列にする。

    クォートは必要なセルにだけ付ける。改行コードの指定は行の区切りにだけ使い、
    セルの中の改行は変えない（要件定義書 7.1）。表せない文字があれば
    UnicodeEncodeError を出す（呼び出し側で事前に検査する。FR-16）。
    """
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator=_LINE_TERMINATORS[newline]).writerows(rows)
    return buffer.getvalue().encode(_CODECS[encoding])


def replay_changes(result: TidyResult) -> list[list[str]]:
    """元の値に変更の記録を当てはめて、出力される表を組み立てる（設計書 D2）。

    画面は、これと同じ手順で変更後の表を作る。出力ファイル（作業用の値から作る）と
    一致することをテスト P5 で確かめ、変更の記録に漏れがないことを保証する。
    """
    values = {record.index: list(record.cells) for record in result.records}
    for change in result.changes:
        if isinstance(change, (CellTrimmed, FormulaEscaped)):
            values[change.record][change.column] = change.after
        elif isinstance(change, RowRemoved):
            del values[change.record]
    return [values[record.index] for record in result.records if record.index in values]
