"""整形処理のテスト（FR-04, 07, 08, 18, 20〜24, 30, 31, 48、受け入れ基準 2〜5・8・13〜15・17・19・20・22）。"""

import pytest

from csv_tidy.core.errors import EmptyDataError
from csv_tidy.core.models import CellTrimmed, IssueCode, Level, RemoveReason, RowRemoved, TidyOptions
from csv_tidy.core.parsing import parse
from csv_tidy.core.pipeline import Pipeline, default_steps, run_steps
from csv_tidy.core.steps import (
    CharScanStep,
    TidyContext,
    TrimStep,
    describe_char,
    trim_cell,
)


def tidy(text, **options):
    return run_steps(parse(text), TidyOptions(**options))


def output_rows(ctx):
    """出力される行（ヘッダーと、削除されなかったデータ行）の値。"""
    return [ctx.values[ctx.header]] + [ctx.values[i] for i in ctx.data_rows()]


def issues_of(ctx, code):
    return [issue for issue in ctx.issues if issue.code is code]


def removed_of(ctx, reason):
    return [c.record for c in ctx.changes if isinstance(c, RowRemoved) and c.reason is reason]


# --- 空白トリム（FR-20） --------------------------------------------------------


def test_trims_half_and_full_width_spaces_but_keeps_inner_space():
    """受け入れ基準 2。"""
    ctx = tidy('名前,氏名\n"  山田　",山田　太郎\n')
    assert output_rows(ctx)[1] == ["山田", "山田　太郎"]
    assert ctx.changes == [CellTrimmed(record=1, column=0, before="  山田　", after="山田")]


def test_trims_tab_and_nbsp():
    """受け入れ基準 15: NBSP は取り除く。"""
    assert trim_cell("\t 値 \t") == "値"


@pytest.mark.parametrize("char", ["\u0085", " ", "​", "、", "\r", "\n"])
def test_does_not_trim_other_characters(char):
    """受け入れ基準 15: U+0085 や U+2028 など、決めた 4 種類以外は取り除かない。"""
    assert trim_cell(f"{char}値{char}") == f"{char}値{char}"


def test_trim_applies_to_header_and_short_rows():
    """FR-20・FR-23: ヘッダーと列数の違う行にもトリムをかける。"""
    ctx = tidy(" h1 ,h2\n a \n")
    assert output_rows(ctx) == [["h1", "h2"], ["a"]]


def test_trim_off_keeps_values():
    """受け入れ基準 17: トリムをオフにすると値は変わらない。"""
    ctx = tidy("h\n  a  \n", trim=False)
    assert output_rows(ctx)[1] == ["  a  "]
    assert ctx.changes == []


def test_records_are_not_modified():
    """元の値（records）は書き換えない。"""
    records = parse("h\n a \n")
    run_steps(records, TidyOptions())
    assert records[1].cells == (" a ",)


# --- ヘッダー行（FR-04, FR-08） --------------------------------------------------


def test_leading_blank_rows_are_skipped_and_reported():
    """受け入れ基準 20: 先頭の空行 2 行を飛ばし、3 行目がヘッダーになる。"""
    ctx = tidy("\n,,\n名前,年齢\n山田,30\n")
    assert ctx.header == 2
    assert removed_of(ctx, RemoveReason.LEADING_BLANK) == [0, 1]
    [info] = issues_of(ctx, IssueCode.LEADING_BLANK)
    assert info.level is Level.INFO
    assert "2 行" in info.detail


def test_whitespace_only_leading_row_is_blank_after_trim():
    ctx = tidy("　, \n名前\n")
    assert ctx.header == 1


def test_whitespace_only_leading_row_is_header_without_trim():
    ctx = tidy("　, \n名前\n", trim=False)
    assert ctx.header == 0


def test_only_blank_rows_raise_empty_data_error():
    """受け入れ基準 19: 空行だけのファイルは「データがありません」。"""
    with pytest.raises(EmptyDataError):
        tidy("\n,,\n \n")


def test_header_only_is_processed_and_reported():
    """受け入れ基準 19: ヘッダーだけのファイルは処理し、情報を返す。"""
    ctx = tidy("名前,年齢\n")
    assert output_rows(ctx) == [["名前", "年齢"]]
    [info] = issues_of(ctx, IssueCode.NO_DATA_ROWS)
    assert info.level is Level.INFO


def test_header_with_only_blank_rows_after_it_has_no_data_rows():
    ctx = tidy("名前\n\n,\n")
    assert issues_of(ctx, IssueCode.NO_DATA_ROWS)


# --- 空行の削除（FR-21, FR-23, FR-24） -------------------------------------------


def test_blank_rows_are_removed_regardless_of_column_count():
    """受け入れ基準 3: 空行とトリム後に空になる行を削除し、ヘッダーは残す。"""
    ctx = tidy("h1,h2\na,b\n\n,\n , 　\nc,d\n")
    assert output_rows(ctx) == [["h1", "h2"], ["a", "b"], ["c", "d"]]
    assert removed_of(ctx, RemoveReason.EMPTY) == [2, 3, 4]


def test_whitespace_row_is_not_blank_when_trim_is_off():
    """FR-24: 空行の判定はトリムの後の値で行う。トリムがオフなら空白だけの行は残る。"""
    ctx = tidy("h\n \n", trim=False)
    assert removed_of(ctx, RemoveReason.EMPTY) == []


def test_remove_empty_off_keeps_blank_rows():
    """受け入れ基準 17: 空行の削除をオフにすると、空行は残る。"""
    ctx = tidy("h\n\na\n", remove_empty=False)
    assert output_rows(ctx) == [["h"], [], ["a"]]


# --- 列数の検査（FR-30, FR-31） --------------------------------------------------


def test_rows_with_different_column_count_are_warned_and_kept():
    """受け入れ基準 5: 列数の違う行があっても処理は止まらず、警告して列数を変えずに出力する。"""
    ctx = tidy("h1,h2,h3,h4\na,b,c,d\na,b\na,b,c,d,e\n")
    assert output_rows(ctx)[2:] == [["a", "b"], ["a", "b", "c", "d", "e"]]
    warnings = issues_of(ctx, IssueCode.COLUMN_COUNT)
    assert [(w.record, w.detail) for w in warnings] == [(2, "列数 2（ヘッダーは 4）"), (3, "列数 5（ヘッダーは 4）")]
    assert all(w.level is Level.WARNING for w in warnings)


def test_removed_blank_rows_are_not_warned():
    """FR-21: 削除した空行は列数の警告の対象にしない。"""
    ctx = tidy("h1,h2,h3\n\n,\n")
    assert issues_of(ctx, IssueCode.COLUMN_COUNT) == []


def test_kept_blank_rows_are_not_warned():
    ctx = tidy("h1,h2,h3\n\n", remove_empty=False)
    assert issues_of(ctx, IssueCode.COLUMN_COUNT) == []


# --- 重複（FR-22） ---------------------------------------------------------------


def test_duplicates_are_reported_but_not_removed_by_default():
    """受け入れ基準 22: 初期状態では削除せず、「何行目と同じ」かを知らせる。"""
    ctx = tidy("名前,年齢\n山田,30\n鈴木,20\n山田,30\n")
    assert len(output_rows(ctx)) == 4
    [info] = issues_of(ctx, IssueCode.DUPLICATE)
    assert (info.level, info.record, info.related_record, info.detail) == (Level.INFO, 3, 1, "2 行目と同じ")


def test_duplicates_after_trim_are_removed_when_enabled():
    """受け入れ基準 4: トリム後に一致する 2 行のうち、1 行目だけが残る。"""
    ctx = tidy("名前,年齢\n山田,30\n 山田 ,30　\n", dedupe=True)
    assert output_rows(ctx) == [["名前", "年齢"], ["山田", "30"]]
    assert [c for c in ctx.changes if isinstance(c, RowRemoved)] == [
        RowRemoved(record=2, reason=RemoveReason.DUPLICATE, duplicate_of=1)
    ]


def test_omitted_cells_and_empty_cells_are_not_duplicates():
    """受け入れ基準 8: `a,b`（2 列）と `a,b,,`（4 列）は重複ではない。"""
    ctx = tidy("h1,h2,h3,h4\na,b\na,b,,\n", dedupe=True)
    assert removed_of(ctx, RemoveReason.DUPLICATE) == []
    assert output_rows(ctx)[1] == ["a", "b"]  # 列数は変わらない
    assert [w.record for w in issues_of(ctx, IssueCode.COLUMN_COUNT)] == [1]


def test_rows_differing_only_by_zero_width_space_are_not_duplicates():
    """受け入れ基準 14: ゼロ幅スペースだけが違う行は重複にならず、警告される。"""
    ctx = tidy("h\n山田\n山​田\n", dedupe=True)
    assert removed_of(ctx, RemoveReason.DUPLICATE) == []
    [warning] = issues_of(ctx, IssueCode.INVISIBLE_CHAR)
    assert (warning.record, warning.column) == (2, 0)
    assert "ゼロ幅スペース" in warning.detail


def test_header_is_not_treated_as_duplicate():
    """FR-23: ヘッダーと同じ内容のデータ行は、ヘッダーとの重複にはしない。"""
    ctx = tidy("h\nh\nh\n", dedupe=True)
    assert removed_of(ctx, RemoveReason.DUPLICATE) == [2]


def test_blank_rows_are_not_deduplicated():
    ctx = tidy("h\n\n\n", remove_empty=False, dedupe=True)
    assert removed_of(ctx, RemoveReason.DUPLICATE) == []


# --- 文字の検査（FR-07, FR-18） ---------------------------------------------------


@pytest.mark.parametrize(
    ("char", "code", "name"),
    [
        ("\x07", IssueCode.CONTROL_CHAR, "制御文字（U+0007）"),
        ("\x1a", IssueCode.CONTROL_CHAR, "制御文字（U+001A）"),
        ("\x7f", IssueCode.CONTROL_CHAR, "DEL（U+007F）"),
        ("\x85", IssueCode.CONTROL_CHAR, "C1 制御文字（U+0085）"),
        ("\x9f", IssueCode.CONTROL_CHAR, "C1 制御文字（U+009F）"),
        ("​", IssueCode.INVISIBLE_CHAR, "ゼロ幅スペース（U+200B）"),
        ("‌", IssueCode.INVISIBLE_CHAR, "ゼロ幅非接合子（U+200C）"),
        ("‍", IssueCode.INVISIBLE_CHAR, "ゼロ幅接合子（U+200D）"),
        ("⁠", IssueCode.INVISIBLE_CHAR, "単語結合子（U+2060）"),
        ("﻿", IssueCode.INVISIBLE_CHAR, "BOM（ファイルの途中）（U+FEFF）"),
    ],
)
def test_control_and_invisible_characters_are_warned_and_kept(char, code, name):
    """受け入れ基準 14: 警告するが、値は変えない。"""
    ctx = tidy(f"h\na{char}b\n")
    [warning] = issues_of(ctx, code)
    assert (warning.level, warning.record, warning.column, warning.detail) == (Level.WARNING, 1, 0, name)
    assert output_rows(ctx)[1] == [f"a{char}b"]


@pytest.mark.parametrize("char", ["\t", "\n", "\r", " ", " ", "　", "あ"])
def test_allowed_characters_are_not_warned(char):
    ctx = tidy(f'h\n"a{char}b"\n')
    assert issues_of(ctx, IssueCode.CONTROL_CHAR) == []
    assert issues_of(ctx, IssueCode.INVISIBLE_CHAR) == []


def test_same_character_repeated_in_a_cell_is_one_issue():
    ctx = tidy("h\na​b​c\n")
    assert len(issues_of(ctx, IssueCode.INVISIBLE_CHAR)) == 1


def test_describe_char_for_other_control():
    assert describe_char("\x01") == "制御文字（U+0001）"


def test_multiline_cell_is_reported_as_info():
    """FR-07: 複数行にまたがるセルを情報として知らせる。"""
    ctx = tidy('h1,h2\na,"1行目\n2行目"\n')
    [info] = issues_of(ctx, IssueCode.MULTILINE_CELL)
    assert (info.level, info.record, info.column) == (Level.INFO, 1, 1)
    assert "2〜3 行目" in info.detail


# --- 数式化の警告（FR-48） --------------------------------------------------------


def test_cell_that_becomes_formula_like_after_trim_is_warned():
    """受け入れ基準 13: `␣=1+1` はトリム後に警告される。値は `=1+1` のまま。"""
    ctx = tidy("h1,h2\n =1+1,x\n")
    [warning] = issues_of(ctx, IssueCode.FORMULA_LIKE)
    assert (warning.level, warning.record, warning.column) == (Level.WARNING, 1, 0)
    assert output_rows(ctx)[1] == ["=1+1", "x"]


@pytest.mark.parametrize("value", ["=1+1", "-5", "+81", "@sum"])
def test_originally_formula_like_cells_are_not_warned(value):
    """受け入れ基準 13: 元から `=1+1` や `-5` だったセルは警告しない。"""
    ctx = tidy(f"h\n{value}\n")
    assert issues_of(ctx, IssueCode.FORMULA_LIKE) == []


def test_formula_check_skips_removed_rows():
    ctx = tidy("h\n =1\n=1\n", dedupe=True)
    # 2 行目はトリムで =1 になり警告。3 行目は元から =1 なので警告しない
    assert [w.record for w in issues_of(ctx, IssueCode.FORMULA_LIKE)] == [1]
    assert removed_of(ctx, RemoveReason.DUPLICATE) == [2]


# --- 処理の順番（FR-24） ---------------------------------------------------------


def test_default_step_order():
    names = [type(step).__name__ for step in default_steps()]
    assert names == [
        "CharScanStep",
        "TrimStep",
        "HeaderStep",
        "EmptyRowStep",
        "ColumnCountStep",
        "DedupeStep",
        "FormulaStep",
        "DataRowsStep",
        "EncodabilityStep",
    ]


def test_pipeline_runs_given_steps_in_order():
    ctx = TidyContext(records=parse("h\n a​\n"), options=TidyOptions())
    Pipeline([TrimStep(), CharScanStep()]).run(ctx)
    assert ctx.values[1] == ["a​"]
    assert ctx.header is None  # HeaderStep は実行していない
    assert ctx.data_rows() == []
    assert ctx.output_rows() == []
