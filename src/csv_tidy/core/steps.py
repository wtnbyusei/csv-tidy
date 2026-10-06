"""整形処理の各段階（設計書 7.2 の Step、FR-18〜25, 30〜31, 48）。

各 Step は同じ形（`apply(ctx)`）をとり、作業用の値（`ctx.values`）を書き換えたり、
変更（`ctx.changes`）や課題（`ctx.issues`）を記録したりする。元の値
（`ctx.records`）は書き換えない。どの順番で実行するかは pipeline.py で決める。
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from .errors import EmptyDataError
from .models import (
    CellTrimmed,
    Change,
    FormulaEscaped,
    Issue,
    IssueCode,
    Level,
    OutputEncoding,
    Record,
    RemoveReason,
    RowRemoved,
    TidyOptions,
)
from .parsing import find_header, is_blank

# 前後から取り除く空白（FR-20）。ここに挙げた文字だけを取り除く。
# str.strip() を引数なしで使うと U+0085 や U+2028 なども消えてしまうため、文字を明示する。
TRIM_CHARS = " \t 　"

# 制御文字（FR-18 (1)）: タブ・LF・CR を除く U+0001〜U+001F、DEL、C1 制御文字。
# NUL（U+0000）は読み込みの段階で拒否している（FR-17）。
_CONTROL = re.compile("[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")

# 見えない文字（FR-18 (2)）: ゼロ幅文字と、ファイルの途中にある BOM。
_INVISIBLE = re.compile("[​‌‍⁠﻿]")
# 制御文字か見えない文字のどちらか。行ごとにまとめて調べ、該当する行だけを詳しく調べる
_ANY_SUSPICIOUS = re.compile(f"{_CONTROL.pattern}|{_INVISIBLE.pattern}")
_INVISIBLE_NAMES = {
    "​": "ゼロ幅スペース",
    "‌": "ゼロ幅非接合子",
    "‍": "ゼロ幅接合子",
    "⁠": "単語結合子",
    "﻿": "BOM（ファイルの途中）",
}

# 表計算ソフトで数式として扱われうる先頭の文字（FR-48, FR-49）。
# 日本語の環境では全角の文字も数式として扱われることがある（OWASP の CSV Injection）
FORMULA_PREFIXES = ("=", "+", "-", "@", "＝", "＋", "－", "＠")

# 無害化の対象にする先頭の文字（FR-49）。数式の文字に、タブ・CR・LF を加える（OWASP の CSV Injection）
ESCAPE_PREFIXES = (*FORMULA_PREFIXES, "\t", "\r", "\n")

# 数値としてそのまま読める値（符号・半角数字・小数点・指数だけ）。数式にならないので無害化しない。
# \d は全角の数字にも当たるので、半角の [0-9] と書く
_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


@dataclass
class TidyContext:
    """整形処理の作業用の領域（設計書 7.2）。"""

    records: list[Record]
    options: TidyOptions
    values: list[list[str]] = field(init=False)
    removed: set[int] = field(default_factory=set)
    header: int | None = None
    changes: list[Change] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.values = [list(record.cells) for record in self.records]

    def output_rows(self) -> list[int]:
        """出力する行（ヘッダーと、削除していないデータ行）の位置。"""
        if self.header is None:
            return []
        return [self.header, *self.data_rows()]

    def data_rows(self) -> list[int]:
        """ヘッダーより後ろの、まだ削除していない行の位置。"""
        if self.header is None:
            return []
        return [i for i in range(self.header + 1, len(self.records)) if i not in self.removed]

    def remove(self, position: int, reason: RemoveReason, duplicate_of: int | None = None) -> None:
        self.removed.add(position)
        self.changes.append(RowRemoved(record=position, reason=reason, duplicate_of=duplicate_of))


class Step(Protocol):
    """整形処理の 1 段階。"""

    def apply(self, ctx: TidyContext) -> None: ...


def describe_char(char: str) -> str:
    """課題の説明に使う、文字の名前と番号。"""
    code = f"U+{ord(char):04X}"
    if char in _INVISIBLE_NAMES:
        return f"{_INVISIBLE_NAMES[char]}（{code}）"
    if char == "\x7f":
        return f"DEL（{code}）"
    if "\x80" <= char <= "\x9f":
        return f"C1 制御文字（{code}）"
    return f"制御文字（{code}）"


class CharScanStep:
    """制御文字・見えない文字・複数行のセルを見つけて知らせる。値は変えない（FR-07, FR-18）。

    元の値（読み込んだままの値）を調べる。
    """

    def apply(self, ctx: TidyContext) -> None:
        for record in ctx.records:
            # 大きなファイルでも速く終わるよう、該当する文字も複数行のセルもない行は飛ばす
            if not record.is_multiline and not _ANY_SUSPICIOUS.search("".join(record.cells)):
                continue
            for column, cell in enumerate(record.cells):
                self._scan(ctx, record.index, column, cell, _CONTROL, IssueCode.CONTROL_CHAR)
                self._scan(ctx, record.index, column, cell, _INVISIBLE, IssueCode.INVISIBLE_CHAR)
                if record.is_multiline and ("\n" in cell or "\r" in cell):
                    ctx.issues.append(
                        Issue(
                            level=Level.INFO,
                            code=IssueCode.MULTILINE_CELL,
                            detail=f"{record.line_start}〜{record.line_end} 行目にまたがるセル",
                            record=record.index,
                            column=column,
                        )
                    )

    @staticmethod
    def _scan(ctx: TidyContext, record: int, column: int, cell: str, pattern: re.Pattern[str], code: IssueCode) -> None:
        # 同じセルに同じ文字が何回あっても、課題は 1 つにまとめる
        for char in dict.fromkeys(pattern.findall(cell)):
            ctx.issues.append(
                Issue(level=Level.WARNING, code=code, detail=describe_char(char), record=record, column=column)
            )


def trim_cell(value: str) -> str:
    """セルの前後から TRIM_CHARS の文字だけを取り除く（FR-20）。"""
    return value.strip(TRIM_CHARS)


class TrimStep:
    """セルの前後の空白を取り除く。ヘッダーや列数の違う行にも適用する（FR-20, FR-23）。"""

    def apply(self, ctx: TidyContext) -> None:
        if not ctx.options.trim:
            return
        for position, row in enumerate(ctx.values):
            for column, before in enumerate(row):
                after = trim_cell(before)
                if after != before:
                    row[column] = after
                    ctx.changes.append(CellTrimmed(record=position, column=column, before=before, after=after))


class HeaderStep:
    """先頭の空行を飛ばしてヘッダー行を決める（FR-04, FR-08）。

    トリムが有効ならトリム後の値で空行を判定する（FR-21）。飛ばした行は出力しない。
    """

    def apply(self, ctx: TidyContext) -> None:
        header = find_header(ctx.values)
        if header is None:
            raise EmptyDataError()
        ctx.header = header
        for position in range(header):
            ctx.remove(position, RemoveReason.LEADING_BLANK)
        if header:
            ctx.issues.append(
                Issue(
                    level=Level.INFO,
                    code=IssueCode.LEADING_BLANK,
                    detail=f"先頭の空行 {header} 行を飛ばしました",
                    record=header,
                )
            )


class EmptyRowStep:
    """すべてのセルが空の行を、列数にかかわらず削除する（FR-21）。ヘッダーは対象外（FR-23）。"""

    def apply(self, ctx: TidyContext) -> None:
        if not ctx.options.remove_empty:
            return
        for position in ctx.data_rows():
            if is_blank(ctx.values[position]):
                ctx.remove(position, RemoveReason.EMPTY)


class ColumnCountStep:
    """ヘッダーと列数が違う行を知らせる。値と列数は変えない（FR-30, FR-31）。

    空行は列数の検査の対象にしない（空行は空行の削除で扱う）。
    """

    def apply(self, ctx: TidyContext) -> None:
        assert ctx.header is not None
        width = len(ctx.values[ctx.header])
        for position in ctx.data_rows():
            row = ctx.values[position]
            if len(row) != width and not is_blank(row):
                ctx.issues.append(
                    Issue(
                        level=Level.WARNING,
                        code=IssueCode.COLUMN_COUNT,
                        detail=f"列数 {len(row)}（ヘッダーは {width}）",
                        record=position,
                    )
                )


class DedupeStep:
    """列数と値がすべて同じ行を重複として見つける（FR-22）。

    重複の削除が有効なら 2 件目以降を削除し、無効なら情報として知らせるだけにする。
    値の比較はトリムなどの後の値で行う。ヘッダーと空行は対象外。
    """

    def apply(self, ctx: TidyContext) -> None:
        first_seen: dict[tuple[str, ...], int] = {}
        for position in ctx.data_rows():
            row = ctx.values[position]
            if is_blank(row):
                continue
            key = tuple(row)
            if key not in first_seen:
                first_seen[key] = position
                continue
            original = first_seen[key]
            if ctx.options.dedupe:
                ctx.remove(position, RemoveReason.DUPLICATE, duplicate_of=original)
            else:
                ctx.issues.append(
                    Issue(
                        level=Level.INFO,
                        code=IssueCode.DUPLICATE,
                        detail=f"{ctx.records[original].line_start} 行目と同じ",
                        record=position,
                        related_record=original,
                    )
                )


class FormulaStep:
    """整形によって先頭が = + - @ になったセルを知らせる。値は変えない（FR-48）。

    元から先頭がこれらの文字だったセルは対象にしない。
    """

    def apply(self, ctx: TidyContext) -> None:
        for position, row in enumerate(ctx.values):
            original = ctx.records[position].cells
            # 削除した行と、値が変わっていない行は調べない
            if position in ctx.removed or tuple(row) == original:
                continue
            for column, value in enumerate(row):
                if value.startswith(FORMULA_PREFIXES) and not original[column].startswith(FORMULA_PREFIXES):
                    ctx.issues.append(
                        Issue(
                            level=Level.WARNING,
                            code=IssueCode.FORMULA_LIKE,
                            detail=f"整形の結果、「{value[0]}」で始まる値になりました（表計算ソフトで数式として扱われるおそれがあります）",
                            record=position,
                            column=column,
                        )
                    )


def needs_escape(value: str) -> bool:
    """表計算ソフトで数式として扱われるおそれがあり、無害化が必要か（FR-49）。"""
    return value.startswith(ESCAPE_PREFIXES) and _NUMBER.fullmatch(value) is None


class FormulaEscapeStep:
    """出力するセル（ヘッダーを含む）のうち、数式として扱われうる値の先頭に `'` を付ける（FR-49）。

    数値として読める値（`-5` など）は対象外。ほかの処理の後、出力の直前に行う。
    """

    def apply(self, ctx: TidyContext) -> None:
        if not ctx.options.escape_formulas:
            return
        for position in ctx.output_rows():
            row = ctx.values[position]
            for column, before in enumerate(row):
                if needs_escape(before):
                    after = "'" + before
                    row[column] = after
                    ctx.changes.append(FormulaEscaped(record=position, column=column, before=before, after=after))


class DataRowsStep:
    """ヘッダー行のほかにデータ行がなければ知らせる（FR-08）。"""

    def apply(self, ctx: TidyContext) -> None:
        if not ctx.data_rows():
            ctx.issues.append(
                Issue(level=Level.INFO, code=IssueCode.NO_DATA_ROWS, detail="データ行がありません（ヘッダー行だけです）")
            )


class EncodabilityStep:
    """出力を CP932 にしたとき、CP932 で表せない文字を ERROR として知らせる（FR-16）。

    勝手に置き換えない。ERROR があると出力できない（TidyResult.exportable）。
    """

    def apply(self, ctx: TidyContext) -> None:
        if ctx.options.output_encoding is not OutputEncoding.CP932:
            return
        for position in ctx.output_rows():
            row = ctx.values[position]
            # 大きなファイルでも速く終わるよう、行全体を変換できる行は飛ばす
            if _cp932_encodable("".join(row)):
                continue
            for column, value in enumerate(row):
                for char in dict.fromkeys(c for c in value if not _cp932_encodable(c)):
                    ctx.issues.append(
                        Issue(
                            level=Level.ERROR,
                            code=IssueCode.UNENCODABLE,
                            detail=f"「{char}」（U+{ord(char):04X}）は CP932 で表せません",
                            record=position,
                            column=column,
                        )
                    )


def _cp932_encodable(text: str) -> bool:
    try:
        text.encode("cp932")
    except UnicodeEncodeError:
        return False
    return True

