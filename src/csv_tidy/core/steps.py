"""整形処理の各段階（設計書 7.2 の Step、FR-18〜25, 30〜31, 48）。

各 Step は同じ形（`apply(ctx)`）をとり、作業用の値（`ctx.values`）を書き換えたり、
変更（`ctx.changes`）や課題（`ctx.issues`）を記録したりする。元の値
（`ctx.records`）は書き換えない。どの順番で実行するかは pipeline.py で決める。
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from .errors import EmptyDataError, InvalidColumnsError
from .models import (
    CellTrimmed,
    Change,
    ColumnSpec,
    FormulaEscaped,
    HeaderRenamed,
    Issue,
    IssueCode,
    Level,
    OutputEncoding,
    Record,
    RemoveReason,
    RenameReason,
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
    width: int = 0  # 列数（ColumnPlanStep が決める。FR-60）
    plan: tuple[ColumnSpec, ...] = ()  # 列の計画（ColumnPlanStep が決める。設計書 15.2）

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

    def kept_sources(self) -> list[int]:
        """出力する列（元の何列目か）を、出力の順番に並べたもの。"""
        return [spec.source for spec in self.plan if spec.keep]

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


class ColumnPlanStep:
    """列数を数え、列の計画を決める（FR-60, FR-61, FR-62。設計書 15.1・15.2）。

    列数は、ヘッダーと空行でないデータ行のうち、いちばん多い列数にする（空行は列数の検査と
    同じく数えない）。`columns` が None なら、全列を元の順番で出力し、すべて比べる計画にする。
    重複の判定（DedupeStep）が比べる列を使うので、ヘッダーを決めた直後に行う。
    """

    def apply(self, ctx: TidyContext) -> None:
        assert ctx.header is not None
        width = len(ctx.values[ctx.header])
        for position in range(ctx.header + 1, len(ctx.values)):
            row = ctx.values[position]
            if len(row) > width and not is_blank(row):
                width = len(row)
        ctx.width = width
        columns = ctx.options.columns
        if columns is None:
            ctx.plan = tuple(ColumnSpec(source=source) for source in range(width))
            return
        # 列の並べ替え（0 から列数−1 までがちょうど 1 回ずつ）でなければ受け付けない（設計書 V2）
        if sorted(spec.source for spec in columns) != list(range(width)):
            raise InvalidColumnsError(width=width)
        ctx.plan = tuple(columns)


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
    """比べる列の値がすべて同じ行を重複として見つける（FR-22, FR-65）。

    重複の削除が有効なら 2 件目以降を削除し、無効なら情報として知らせるだけにする。
    値の比較はトリムなどの後の値で行う。ヘッダーと空行は対象外。セルがないことと
    空のセルは区別する（セルがない位置は None にする）。比べる列がなければ何もしない。
    初期状態（全列を比べる）では、列数と値がすべて同じ行を重複とする v0.1 と同じ判定になる。
    """

    def apply(self, ctx: TidyContext) -> None:
        compare = [spec.source for spec in ctx.plan if spec.compare]
        if not compare:
            return
        first_seen: dict[tuple[str | None, ...], int] = {}
        for position in ctx.data_rows():
            row = ctx.values[position]
            if is_blank(row):
                continue
            length = len(row)
            key = tuple(row[source] if source < length else None for source in compare)
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


_NAME_NEWLINES = re.compile(r"\r\n|\r|\n")


def tidy_names(names: list[str], sources: list[int]) -> list[str]:
    """列名をあるべき姿（H-1 名前がある、H-2 重複しない、H-4 改行がない）にそろえる（FR-66）。

    `names` は出力する列の名前を出力の順番に並べたもの、`sources` はそれぞれの元の何列目か。
    (1) 改行を半角スペースに、(2) 空の名前を「列N」（N は元の何列目か、1 から数える）に、
    (3) 同じ名前の 2 つ目以降に「_2」「_3」…を付ける（ほかの列名と同じになるなら番号を進める）。
    """
    names = [_NAME_NEWLINES.sub(" ", name) for name in names]
    names = [name or f"列{source + 1}" for name, source in zip(names, sources, strict=True)]
    existing = set(names)
    seen: set[str] = set()
    result = []
    for name in names:
        if name in seen:
            number = 2
            while f"{name}_{number}" in existing or f"{name}_{number}" in seen:
                number += 1
            name = f"{name}_{number}"
        seen.add(name)
        result.append(name)
    return result


class HeaderNameStep:
    """出力する列の名前を決める（FR-63, FR-66。設計書 15.2）。

    利用者が書き換えた名前は `HeaderRenamed`（理由 renamed）として記録する。列名を整える処理が
    オンなら直した列ごとに `HeaderRenamed`（理由 tidied）を記録し、オフならあるべき姿でない
    名前を警告する。列名の変更は、ヘッダー行の元の位置のセルの変更として記録する。
    """

    def apply(self, ctx: TidyContext) -> None:
        assert ctx.header is not None
        header = ctx.values[ctx.header]
        kept = [spec for spec in ctx.plan if spec.keep]
        sources = [spec.source for spec in kept]
        names = []
        for spec in kept:
            current = header[spec.source] if spec.source < len(header) else ""
            if spec.name is not None and spec.name != current:
                self._rename(ctx, spec.source, spec.name, RenameReason.RENAMED)
                current = spec.name
            names.append(current)
        if ctx.options.tidy_names:
            for source, before, after in zip(sources, names, tidy_names(names, sources), strict=True):
                if after != before:
                    self._rename(ctx, source, after, RenameReason.TIDIED)
        else:
            self._warn(ctx, names, sources)

    @staticmethod
    def _rename(ctx: TidyContext, column: int, after: str, reason: RenameReason) -> None:
        assert ctx.header is not None
        row = ctx.values[ctx.header]
        # ヘッダーにない列の名前は、その位置まで空のセルを足してから入れる（設計書 15.5 の 1）
        if column >= len(row):
            row.extend([""] * (column + 1 - len(row)))
        before = row[column]
        row[column] = after
        ctx.changes.append(HeaderRenamed(record=ctx.header, column=column, before=before, after=after, reason=reason))

    @staticmethod
    def _warn(ctx: TidyContext, names: list[str], sources: list[int]) -> None:
        seen: set[str] = set()
        for name, source in zip(names, sources, strict=True):
            problems = []
            if name == "":
                problems.append("列名が空です")
            if _NAME_NEWLINES.search(name):
                problems.append("列名に改行があります")
            if name in seen:
                problems.append(f"列名「{name}」がほかの列と重複しています")
            seen.add(name)
            for problem in problems:
                ctx.issues.append(
                    Issue(
                        level=Level.WARNING,
                        code=IssueCode.HEADER_NAME,
                        detail=problem,
                        record=ctx.header,
                        column=source,
                    )
                )


def needs_escape(value: str) -> bool:
    """表計算ソフトで数式として扱われるおそれがあり、無害化が必要か（FR-49）。"""
    return value.startswith(ESCAPE_PREFIXES) and _NUMBER.fullmatch(value) is None


class FormulaEscapeStep:
    """出力するセル（ヘッダーを含む）のうち、数式として扱われうる値の先頭に `'` を付ける（FR-49）。

    数値として読める値（`-5` など）は対象外。出力しない列のセルも対象外（FR-67）。
    ほかの処理の後、出力の直前に行う。
    """

    def apply(self, ctx: TidyContext) -> None:
        if not ctx.options.escape_formulas:
            return
        kept = sorted(ctx.kept_sources())
        for position in ctx.output_rows():
            row = ctx.values[position]
            for column in kept:
                if column >= len(row):
                    break
                before = row[column]
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
    出力しない列のセルは対象外（FR-67）。
    """

    def apply(self, ctx: TidyContext) -> None:
        if ctx.options.output_encoding is not OutputEncoding.CP932:
            return
        kept = sorted(ctx.kept_sources())
        for position in ctx.output_rows():
            row = ctx.values[position]
            # 大きなファイルでも速く終わるよう、行全体を変換できる行は飛ばす
            if _cp932_encodable("".join(row)):
                continue
            for column in kept:
                if column >= len(row):
                    break
                value = row[column]
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

